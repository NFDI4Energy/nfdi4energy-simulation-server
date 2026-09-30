"""Owned framework history, with filtering before counting and pagination."""
from fastapi_app.persistence.models_db import Task
from fastapi_app.tasks.dependencies import status_service


def list_tasks(request, db, owner_id, framework, cursor, limit):
    query = db.query(Task).filter(Task.user_id == owner_id, Task.framework == framework)
    count = query.count()
    tasks = query.order_by(Task.created_at.desc(), Task.id.desc()).offset(cursor).limit(limit).all()
    service = status_service(request, framework)
    result = [{"task_id": task.id, "scenario_id": task.scenario_id, "framework": task.framework,
               **service.resolve(task.id, task.status, task.error_message),
               "created_at": task.created_at.isoformat() if task.created_at else None} for task in tasks]
    next_cursor = cursor + len(result)
    return {"tasks": result, "count": count, "cursor": next_cursor, "hasMore": next_cursor < count}
