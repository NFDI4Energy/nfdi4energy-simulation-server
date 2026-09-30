from typing import List
from fastapi import APIRouter, Request, Depends, UploadFile, File, Query
from sqlalchemy.orm import Session
from fastapi_app.authentication.auth import require_login
from fastapi_app.persistence.database_dependencies import get_db
from fastapi_app.tasks.listing import list_tasks
from fastapi_app.tasks.submission import SubmissionError

router = APIRouter(prefix="/api/mosaik", tags=["Mosaik"])


@router.post("/submit")
def submit(request: Request, scenario_file: UploadFile = File(...),
           resource_files: List[UploadFile] = File(default=[]),
           user=Depends(require_login), db: Session = Depends(get_db)):
    if not request.app.state.settings.mosaik_enabled:
        raise SubmissionError("Mosaik submissions are disabled", "framework_disabled", 503)
    if resource_files:
        raise SubmissionError("Mosaik currently accepts a self-contained export only", "unsupported_resources")
    return request.app.state.mosaik_submission.submit(scenario_file, [], user.id, db)


@router.get("/tasks")
def tasks(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
          user=Depends(require_login), db: Session = Depends(get_db)):
    return list_tasks(request, db, user.id, "mosaik", cursor, limit)
