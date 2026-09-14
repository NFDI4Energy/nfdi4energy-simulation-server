import os
import json
import uuid
import asyncio
import websockets
import pika
import redis
import time
import traceback
import requests
from typing import Optional

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
RESOURCES_DIR = os.environ.get("RESOURCES_DIR", "/data/resources")
RESULTS_DIR = os.environ.get("RESULTS_DIR", "/data/results")
VILLAS_QUEUE = os.environ.get("VILLAS_QUEUE", "villas_requests")


def connect_rabbitmq():
    print("connect_rabbitmq called ...")
    while True:
        try:
            rmq = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            return rmq
        except pika.exceptions.AMQPConnectionError:
            print("Waiting for RabbitMQ...")
            time.sleep(3)


def connect_redis():
    return redis.Redis(host=REDIS_HOST, port=6379, db=0)

# To test that requests work: get status!
async def run_villas_node(config: dict, task_id: str) -> dict:
    print("run_villas_node called called...")
    result = {"status": "success", "task_id": task_id}
    logs = []
    sim_progress = 0.0 # This will be a timer to simulate a simulator
    payload = json.loads('{"config":' + str(json.dumps(config) +'}'))
    print("the payload:")
    print(payload)

    try:
        response = requests.post("http://villas-node:8080/api/v2/restart", json=payload)
        print({response})
 #       status_code = msg["status_code"]
 #       print(f"[{task_id}] Status: {status}")
 #       if status_code != 200:
 #           raise Exception("Something went wrong")

    except Exception as e:
        result["status"] = "error"
        result["error"] = traceback.format_exc()

    return result


# TODO: Change scenario description to config
def on_request(ch, method, props, body):
    print("on_request called...")
    task_id = None
    try:
        msg = json.loads(body)
        task_id = msg["task_id"]
        scenario = msg["scenario"]  # TODO: take a closer look at the body
        print(f"[{task_id}] Received task")

        r = connect_redis()
        r.hset(f"task:{task_id}", "status", "RUNNING")

        # Get Config
        config_path = os.path.join(RESOURCES_DIR, task_id, "scenario.json")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                scenario = json.load(f)

        # Run VILLASnode
        result = asyncio.run(run_villas_node(scenario, task_id))

        # Write "result" into result file
        result_dir = os.path.join(RESULTS_DIR, task_id)
        os.makedirs(result_dir, exist_ok=True)
        output_file = "result.json"
        with open(os.path.join(result_dir, output_file), "w") as f:
            json.dump(result, f)

        # TODO: How to handlle status field?
        if result["status"] == "success":
            r.hset(f"task:{task_id}", mapping={"status": "DONE", "files": json.dumps([output_file])})
        else:
            r.hset(f"task:{task_id}", mapping={"status": "ERROR", "error": result.get("error", "Unknown error")})

        print(f"[{task_id}] Finished task with status: {result['status']}")

    except Exception as e:
        print(f"Error processing task {task_id}: {traceback.format_exc()}")
        if task_id:
            r = connect_redis()
            r.hset(f"task:{task_id}", mapping={"status": "ERROR", "error": str(e)})

    ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    print("Starting villas worker...")

    rmq = connect_rabbitmq()
    channel = rmq.channel()
    channel.queue_declare(queue=VILLAS_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)

    print(f"Listening on queue: {VILLAS_QUEUE}")
    channel.basic_consume(queue=VILLAS_QUEUE, on_message_callback=on_request)
    channel.start_consuming()


if __name__ == "__main__":
    main()
