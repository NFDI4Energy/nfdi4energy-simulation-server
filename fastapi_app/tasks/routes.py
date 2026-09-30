from urllib.parse import quote
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from fastapi_app.persistence.database_dependencies import get_db
from fastapi_app.authentication.auth import require_login
from fastapi_app.tasks.dependencies import owned_task, OwnedTask, status_service
from fastapi_app.tasks.listing import list_tasks

router = APIRouter()


@router.get("/check/{task_id}")
def check(request: Request, task: OwnedTask = Depends(owned_task)):
    runtime = status_service(request, task.framework).resolve(task.id, task.status, task.error)
    files = request.app.state.storage.files(task.id)
    return {"task_id": task.id, "framework": task.framework, **runtime, "files": files,
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
    return list_tasks(request, db, user.id, "dacedsx", cursor, limit)
