"""Existing DaceDSX submission API; URL and multipart fields remain unchanged."""
from typing import List
from fastapi import APIRouter, Request, Depends, UploadFile, File
from sqlalchemy.orm import Session

from fastapi_app.authentication.auth import require_login
from fastapi_app.persistence.database_dependencies import get_db

router = APIRouter()


@router.post("/submit")
def submit(request: Request, scenario_file: UploadFile = File(...),
           resource_files: List[UploadFile] = File(default=[]),
           user=Depends(require_login), db: Session = Depends(get_db)):
    return request.app.state.submission.submit(scenario_file, resource_files, user.id, db)
