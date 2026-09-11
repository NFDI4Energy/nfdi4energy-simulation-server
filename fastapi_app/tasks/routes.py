from urllib.parse import quote
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from fastapi_app.persistence.database_dependencies import get_db
from fastapi_app.authentication.auth import require_login
from fastapi_app.persistence.models_db import Task
from fastapi_app.tasks.dependencies import owned_task, OwnedTask

router = APIRouter()


@router.get("/check/{task_id}")
def check(request: Request, task: OwnedTask = Depends(owned_task)):
    runtime = request.app.state.status.resolve(task.id, task.status, task.error)
    files = request.app.state.storage.files(task.id)
    return {"task_id": task.id, **runtime, "files": files,
            "downloads": ["/download/" + quote(task.id, safe="") + "/" + quote(f, safe="/") for f in files]}


@router.get("/list_files/{task_id}")
def list_files(request: Request, task: OwnedTask = Depends(owned_task)):
    if not request.app.state.storage.results(task.id).is_dir():
        return JSONResponse({"error": "No results directory found"}, status_code=404)
    return {"task_id": task.id, "files": request.app.state.storage.files(task.id)}


@router.get("/download/{task_id}/{filename:path}")
def download(filename: str, request: Request, task: OwnedTask = Depends(owned_task)):
    path = request.app.state.storage.result_file(task.id, filename)
    if not path.is_file() or path.name.startswith("."):
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(str(path), filename=path.name)


@router.get("/my-tasks")
def my_tasks(request: Request, cursor: int = Query(0, ge=0),
             limit: int = Query(100, ge=1, le=1000),
             user=Depends(require_login), db: Session = Depends(get_db)):
    query = db.query(Task).filter(Task.user_id == user.id)
    count = query.count()
    tasks = query.order_by(Task.created_at.desc(), Task.id.desc()).offset(cursor).limit(limit).all()
    result = []
    for task in tasks:
        runtime = request.app.state.status.resolve(task.id, task.status, task.error_message)
        result.append({"task_id": task.id, "scenario_id": task.scenario_id, **runtime,
                       "created_at": task.created_at.isoformat() if task.created_at else None})
    next_cursor = cursor + len(result)
    return {"tasks": result, "count": count, "cursor": next_cursor, "hasMore": next_cursor < count}
