"""SSE protocol; the HTTP adapter supplies bounded threaded file access."""
import asyncio
import json
from fastapi_app.frameworks.dacedsx.monitoring.formatting import frontend_event

def sse_message(name, data, event_id=None):
    header = "event: " + name + "\n"
    if event_id is not None:
        header += "id: " + event_id + "\n"
    return header + "data: " + json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n\n"


async def stream_frames(request, read_page, path, cursor, generation, heartbeat_interval=15):
    last_id = request.headers.get("last-event-id")
    if last_id:
        try:
            last_generation, raw_cursor = last_id.rsplit(":", 1)
            last_cursor = max(0, int(raw_cursor))
            generation, cursor = last_generation, last_cursor
        except ValueError:
            pass
    yield sse_message("ready", {"cursor": cursor, "generation": generation})
    last_heartbeat = asyncio.get_running_loop().time()
    while not await request.is_disconnected():
        pending = asyncio.create_task(read_page(path, cursor, 100, generation))
        try:
            # Keep heartbeats independent of a busy file-reader thread pool.
            while not pending.done():
                await asyncio.wait({pending}, timeout=min(1, heartbeat_interval))
                if await request.is_disconnected():
                    return
                now = asyncio.get_running_loop().time()
                if now - last_heartbeat >= heartbeat_interval:
                    last_heartbeat = now
                    yield sse_message("heartbeat", {"cursor": cursor, "generation": generation})
            batch = await pending
        finally:
            if not pending.done():
                pending.cancel()
                try:
                    await pending
                except asyncio.CancelledError:
                    pass
            elif not pending.cancelled():
                pending.exception()
        generation = batch["generation"]
        if batch["reset"]:
            cursor = 0
            yield sse_message("reset", {"cursor": 0, "generation": generation}, generation + ":0")
        for event in batch["rows"]:
            cursor += 1
            yield sse_message("structured-event", {"cursor": cursor, "generation": generation,
                              "event": frontend_event(event)}, generation + ":" + str(cursor))
        now = asyncio.get_running_loop().time()
        if now - last_heartbeat >= heartbeat_interval:
            last_heartbeat = now
            yield sse_message("heartbeat", {"cursor": cursor, "generation": generation})
        await asyncio.sleep(0 if batch["hasMore"] else 1)
