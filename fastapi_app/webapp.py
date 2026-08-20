import os
import json
import uuid
import mimetypes
from typing import List

import redis
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from rabbitmq_client import SimulationQueue, HANDLERS


REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
RESULTS_DIR = os.environ.get("RESULTS_DIR", "/data/results")
RESOURCES_DIR = os.environ.get("RESOURCES_DIR", "/data/resources")

redis_client = redis.Redis(host=REDIS_HOST, port=6379, db=0)

app = FastAPI()

SERVER_ROOT = os.path.dirname(__file__)

app.mount(
    "/static", StaticFiles(directory=os.path.join(SERVER_ROOT, "static")), name="static"
)

templates = Jinja2Templates(directory=os.path.join(SERVER_ROOT, "templates"))


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/submit/{framework}")
async def submit_simulation(framework: str, files: List[UploadFile] = File(...)):
    """Accept uploaded files, save to /data/resources/{task_id}, queue the task."""
    handler = HANDLERS.get(framework)
    if handler is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown framework: '{framework}'. Supported: {list(HANDLERS.keys())}",
        )

    task_id = str(uuid.uuid4())
    task_resources_dir = handler.get_resources_dir(task_id)
    os.makedirs(task_resources_dir, exist_ok=True)

    files_content = []
    for f in files:
        content = await f.read()
        file_path = os.path.join(task_resources_dir, f.filename)
        with open(file_path, "wb") as out:
            out.write(content)
        files_content.append((f.filename, content))

    scenario_json = handler.parse_scenario(files_content)

    queue = SimulationQueue()
    handler.publish(task_id, scenario_json, queue)
    queue.close()

    redis_client.hset(
        f"task:{task_id}",
        mapping={**{"status": "PENDING", "files": "[]", "error": ""}, **handler.get_redis_fields()},
    )

    return JSONResponse(content={"task_id": task_id})


@app.get("/check/{task_id}")
async def check_task(task_id: str):
    data = redis_client.hgetall(f"task:{task_id}")

    if not data:
        return JSONResponse(content={"status": "NOT_FOUND"}, status_code=404)

    status = data[b"status"].decode()
    framework = data.get(b"framework", b"default").decode()
    response = {"task_id": task_id, "status": status, "framework": framework}

    if status == "DONE":
        # Scan actual results directory for files
        task_dir = os.path.join(RESULTS_DIR, task_id)
        files = []
        if os.path.isdir(task_dir):
            for root, _, filenames in os.walk(task_dir):
                for f in filenames:
                    rel = os.path.relpath(os.path.join(root, f), task_dir)
                    files.append(rel)
        response["files"] = files
        response["downloads"] = [f"/download/{task_id}/{f}" for f in files]
    elif status == "ERROR":
        response["error"] = data.get(b"error", b"").decode()

    return JSONResponse(content=response)


@app.get("/list_files/{task_id}")
async def list_files(task_id: str):
    task_dir = os.path.join(RESULTS_DIR, task_id)

    if not os.path.isdir(task_dir):
        return JSONResponse(
            content={"error": "No results directory found"}, status_code=404
        )

    files = []
    for root, _, filenames in os.walk(task_dir):
        for f in filenames:
            rel = os.path.relpath(os.path.join(root, f), task_dir)
            files.append(rel)

    return JSONResponse(content={"task_id": task_id, "files": files})


@app.get("/download/{task_id}/{filename:path}")
async def download_file(task_id: str, filename: str):
    file_path = os.path.join(RESULTS_DIR, task_id, filename)

    if not os.path.isfile(file_path):
        return JSONResponse(content={"error": "File not found"}, status_code=404)

    media_type, _ = mimetypes.guess_type(filename)

    return FileResponse(
        path=file_path,
        filename=os.path.basename(filename),
        media_type=media_type or "application/octet-stream",
    )
