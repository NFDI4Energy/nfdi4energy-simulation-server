from typing import Optional
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from fastapi_app.frameworks.dacedsx.monitoring.models import MonitorPayload
from fastapi_app.frameworks.dacedsx.monitoring.event_stream import stream_frames
from fastapi_app.tasks.dependencies import OwnedTask, owned_task

router = APIRouter()


@router.get("/monitor/{task_id}", response_model=MonitorPayload)
@router.get("/monitor/{task_id}/snapshot", response_model=MonitorPayload)
def snapshot(request: Request, cursor: int = Query(0, ge=0),
             history_index: Optional[int] = Query(None, ge=0), generation: Optional[str] = None,
             task: OwnedTask = Depends(owned_task)):
    return request.app.state.monitor.payload(task.id, cursor, history_index, task.status,
                                            task.error, task.resources, generation)


def page(request, task, filename, key, cursor, limit, generation=None):
    path = request.app.state.storage.result_file(task.id, filename)
    result = request.app.state.events.page(path, cursor, limit, generation)
    result[key] = result.pop("rows")
    return {"task_id": task.id, **result}


@router.get("/monitor/{task_id}/events")
def events(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
           generation: Optional[str] = None, task: OwnedTask = Depends(owned_task)):
    return page(request, task, "events/structured_events.jsonl", "events", cursor, limit, generation)


@router.get("/monitor/{task_id}/metrics")
def metrics(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
            generation: Optional[str] = None, task: OwnedTask = Depends(owned_task)):
    return page(request, task, "events/metrics.jsonl", "metrics", cursor, limit, generation)


@router.get("/monitor/{task_id}/debug/failed-events")
def failed_events(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                  generation: Optional[str] = None, task: OwnedTask = Depends(owned_task)):
    return page(request, task, "debug/failed_event_samples.jsonl", "failedEvents", cursor, limit, generation)


@router.get("/monitor/{task_id}/stream")
async def stream(request: Request, cursor: int = Query(0, ge=0), generation: Optional[str] = None,
                 task: OwnedTask = Depends(owned_task)):
    path = request.app.state.storage.result_file(task.id, "events/structured_events.jsonl")
    async def read_page(*args):
        return await run_in_threadpool(request.app.state.events.page, *args)
    return StreamingResponse(stream_frames(request, read_page, path, cursor, generation),
        media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
