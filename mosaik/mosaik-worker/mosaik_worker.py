"""Minimal RabbitMQ -> Orbit worker for trusted local scenarios."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import time
import traceback
import uuid

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
MOSAIK_WS_URL = os.environ.get("MOSAIK_WS_URL", "ws://mosaik-orbit:8442")
RESULTS_DIR = os.environ.get("RESULTS_DIR", "/data/results")
MOSAIK_QUEUE = os.environ.get("MOSAIK_QUEUE", "mosaik_requests")
BAKE_TIMEOUT = float(os.environ.get("MOSAIK_BAKE_TIMEOUT", "120"))
RUN_TIMEOUT = float(os.environ.get("MOSAIK_RUN_TIMEOUT", "3600"))


def connect_rabbitmq():
    import pika
    while True:
        try:
            return pika.BlockingConnection(pika.ConnectionParameters(
                host=RABBITMQ_HOST, heartbeat=30, socket_timeout=5,
                stack_timeout=10, blocked_connection_timeout=10))
        except pika.exceptions.AMQPConnectionError:
            print("Waiting for RabbitMQ...", flush=True)
            time.sleep(3)


async def run_mosaik_simulation(scenario, task_id):
    from websockets.asyncio.client import connect
    result = {"status": "success", "task_id": task_id, "logs": [], "sim_progress": 0.0}
    command_sent = False
    log_bytes = 0

    async def receive(ws):
        nonlocal log_bytes
        msg = json.loads(await ws.recv())
        if msg.get("$type") == "Log":
            size = len(json.dumps(msg.get("entry")).encode())
            if log_bytes + size <= 2 * 1024 * 1024:
                result["logs"].append(msg.get("entry"))
                log_bytes += size
            else:
                result["logs_truncated"] = True
        if msg.get("$type") == "UpdateSimulationProgress":
            result["sim_progress"] = msg.get("sim_progress", result["sim_progress"])
        return msg

    try:
        # Save JSON includes editor layout; Bake only accepts its declaration.
        if scenario.get("$type") != "Scenario":
            if scenario.get("version") != "1.0" or not isinstance(scenario.get("declaration"), dict):
                raise ValueError("Expected an Orbit Scenario or GUI export version 1.0")
            scenario = scenario["declaration"]
        # Change the output_file param for mosaik-csv writer to make result available in UI
        for sim in (scenario.get("simulators") or {}).values():
            init = sim.get("init_params") or {}
            if "output_file" in init:
                init["output_file"] = os.path.join(
                    RESULTS_DIR, task_id, os.path.basename(str(init["output_file"])))
        async with connect(MOSAIK_WS_URL, open_timeout=15, close_timeout=5,
                           max_size=10 * 1024 * 1024) as ws:
            async with asyncio.timeout(15):
                while (await receive(ws)).get("$type") != "AvailableStarters":
                    pass
            bake_id = str(uuid.uuid4())
            async with asyncio.timeout(BAKE_TIMEOUT):
                command_sent = True
                await ws.send(json.dumps({"$type": "Bake", "id": bake_id, "scenario": scenario}))
                while True:
                    msg = await receive(ws)
                    if msg.get("id") != bake_id:
                        continue
                    if msg.get("$type") == "BakeFailed" or (
                        msg.get("$type") == "UpdateOrbit" and msg.get("problem_free") is False
                    ):
                        return dict(result, status="error", error=msg.get("message", "Scenario has baking problems"))
                    if msg.get("$type") == "UpdateOrbit":
                        result["orbit"] = msg["orbit"]
                        break
            async with asyncio.timeout(RUN_TIMEOUT):
                await ws.send(json.dumps({"$type": "StartSimulation"}))
                while True:
                    msg = await receive(ws)
                    if msg.get("$type") == "UpdateSimulationStatus" and msg.get("status") == "complete":
                        break
                    # Initial idle messages are not proof that execution failed.
    except Exception:
        result.update(status="unknown" if command_sent else "error", error=traceback.format_exc())
    return result


def process_task(task_id, scenario, tracker):
    print(f"[{task_id}] Received task", flush=True)
    root = Path(RESULTS_DIR).resolve()
    result_dir = root / task_id
    if result_dir.is_symlink():
        raise ValueError("Task result directory cannot be a symlink")
    result_dir.resolve().relative_to(root)
    result_dir.mkdir(parents=True, exist_ok=True)
    tracker.hset(f"task:{task_id}", mapping={"status": "RUNNING", "error": ""})
    result = asyncio.run(run_mosaik_simulation(scenario, task_id))

    # Publish a complete file before exposing terminal status or acknowledging.
    fd, temporary = tempfile.mkstemp(prefix=".result-", dir=result_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(result, output, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), 0o644)
        os.replace(temporary, result_dir / "result.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    status = {"success": "DONE", "error": "ERROR", "unknown": "UNKNOWN"}[result["status"]]
    tracker.hset(f"task:{task_id}", mapping={
        "status": status, "files": json.dumps(["result.json"]), "error": result.get("error", "")})
    print(f"[{task_id}] Finished task with status: {status}", flush=True)


def on_request(ch, method, props, body, tracker, executor):
    try:
        msg = json.loads(body)
        task_id, scenario = msg["task_id"], msg["scenario"]
        if not isinstance(task_id, str) or str(uuid.UUID(task_id)) != task_id:
            raise ValueError("Expected a canonical task UUID")
        if not isinstance(scenario, dict) or not scenario:
            raise ValueError("Scenario must be a nonempty object")
        json.dumps(scenario, allow_nan=False)
    except (ValueError, TypeError, KeyError):
        print("Rejected malformed simulation request", flush=True)
        ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
        return
    # Pika I/O and acknowledgement stay on the connection's owning thread.
    future = executor.submit(process_task, task_id, scenario, tracker)
    while not future.done():
        ch.connection.process_data_events(time_limit=1)
    future.result()
    ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    import redis
    if any(not 0 < timeout < float("inf") for timeout in (BAKE_TIMEOUT, RUN_TIMEOUT)):
        raise ValueError("Mosaik timeouts must be finite and positive")
    print("Starting Mosaik worker (trusted local scenarios only)", flush=True)
    rmq = connect_rabbitmq()
    tracker = redis.Redis(host=REDIS_HOST, socket_connect_timeout=5, socket_timeout=5)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            channel = rmq.channel()
            channel.queue_declare(queue=MOSAIK_QUEUE, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=MOSAIK_QUEUE, on_message_callback=
                lambda ch, method, props, body: on_request(ch, method, props, body, tracker, executor))
            print(f"Listening on queue: {MOSAIK_QUEUE}", flush=True)
            channel.start_consuming()
    finally:
        tracker.close()
        if rmq.is_open:
            rmq.close()


if __name__ == "__main__":
    main()
