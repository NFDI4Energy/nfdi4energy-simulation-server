from dataclasses import dataclass
from typing import Optional, List
from fastapi import Depends, Request
from fastapi_app.authentication.auth import require_login
from fastapi_app.persistence.models_db import Task


class TaskNotFound(Exception):
    pass


@dataclass(frozen=True)
class OwnedTask:
    id: str
    status: Optional[str]
    error: Optional[str]
    resources: Optional[List[str]]


def owned_task(task_id: str, request: Request, user=Depends(require_login)):
    # Copy only required fields and close before an SSE response starts.
    with request.app.state.session_factory() as db:
        task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
        if task is None:
            raise TaskNotFound()
        return OwnedTask(task.id, task.status, task.error_message, task.resource_files)
