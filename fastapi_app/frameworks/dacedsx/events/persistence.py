"""Single persistence boundary for API and Kafka event writers."""
import atexit
import fcntl
import json
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi_app.frameworks.dacedsx.events.store import EventStore
from fastapi_app.tasks.storage import TaskStorage, flat_filename
from fastapi_app.core.settings import Settings

SUPPORTED_SCHEMA_VERSIONS = {"1.0"}
REQUIRED_EVENT_FIELDS = {"id", "schema_version", "task_id", "timestamp", "source",
                         "category", "component", "event_code", "message"}
VALID_CATEGORIES = {"PROGRESS", "VALIDATION", "WRAPPER", "SIMULATION", "METRIC",
                    "WARNING", "ERROR", "RESULT"}
_index = None
_thread_lock = threading.RLock()


def _get_index():
    global _index
    if _index is None:
        _index = EventStore()
    return _index


def close_persistence():
    global _index
    with _thread_lock:
        if _index is not None:
            _index.close()
            _index = None


atexit.register(close_persistence)


def default_storage():
    settings = Settings.from_env()
    return TaskStorage(settings.resources_dir, settings.results_dir)


def validate_event(event):
    if not isinstance(event, dict):
        return False, "event must be a JSON object"
    missing = sorted(k for k in REQUIRED_EVENT_FIELDS if not event.get(k))
    if missing:
        return False, "missing required fields: " + ", ".join(missing)
    if str(event.get("schema_version")) not in SUPPORTED_SCHEMA_VERSIONS:
        return False, "unsupported schema_version"
    if not isinstance(event.get("category"), str) or event.get("category") not in VALID_CATEGORIES:
        return False, "invalid category"
    try:
        flat_filename(event["task_id"])
        if not isinstance(event["id"], str):
            raise ValueError("event id must be a string")
        for field in ("timestamp", "source", "component", "event_code", "message"):
            if not isinstance(event[field], str):
                raise ValueError(field + " must be a string")
        if event.get("metadata") is not None and not isinstance(event["metadata"], dict):
            raise ValueError("metadata must be an object")
        json.dumps(event, allow_nan=False)
    except (ValueError, TypeError) as exc:
        return False, str(exc)
    return True, ""


@contextmanager
def task_write_lock(storage, task_id):
    directory = storage.result_file(task_id, "events")
    directory.mkdir(parents=True, mode=0o777, exist_ok=True)
    directory.chmod(0o777)
    path = storage.result_file(task_id, "events/.writer.lock")
    with _thread_lock, open(path, "a+b") as lock:
        os.chmod(path, 0o666)
        # All backend writers take this lock; no fallback to unlocked writes.
        # POSIX record locks interoperate with Java FileChannel.lock and C++ fcntl.
        fcntl.lockf(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.lockf(lock, fcntl.LOCK_UN)


def _append_once(path, event):
    index = _get_index()
    if index.count(path, "event_id=?", (event["id"],)):
        # A local emitter may have written this record before Kafka delivery.
        # Confirm its durability too, including retries after a failed fsync.
        with open(path, "ab") as target:
            os.fsync(target.fileno())
        return False
    path.parent.mkdir(parents=True, mode=0o777, exist_ok=True)
    path.parent.chmod(0o777)
    with open(path, "a+b") as target:
        target.seek(0, os.SEEK_END)
        if target.tell():
            target.seek(-1, os.SEEK_END)
            if target.read(1) != b"\n":
                # Preserve a torn record for diagnostics without merging the next event.
                target.write(b"\n")
        target.write((json.dumps(event, separators=(",", ":"), allow_nan=False) + "\n").encode())
        target.flush()
        os.fsync(target.fileno())
    path.chmod(0o666)
    return True


def append_dead_letter(reason, original_event, task_id=None, storage=None):
    storage = storage or default_storage()
    try:
        target = flat_filename(task_id or "unknown")
    except ValueError:
        target = "unknown"
    row = {"id": "dead_" + str(uuid.uuid4()), "received_at": datetime.now(timezone.utc).isoformat(),
           "reason": reason, "error": reason,
           "event_id": original_event.get("id") if isinstance(original_event, dict) else None,
           "schema_version": original_event.get("schema_version") if isinstance(original_event, dict) else None,
           "original_event": original_event}
    # Invalid non-finite data must still be representable in the dead-letter file.
    row = json.loads(json.dumps(row, default=str), parse_constant=lambda token: token)
    with task_write_lock(storage, target):
        _append_once(storage.result_file(target, "debug/failed_event_samples.jsonl"), row)


def persist_structured_event(event, storage=None):
    storage = storage or default_storage()
    valid, reason = validate_event(event)
    if not valid:
        append_dead_letter(reason, event, event.get("task_id") if isinstance(event, dict) else None, storage)
        return False
    with task_write_lock(storage, event["task_id"]):
        path = storage.result_file(event["task_id"], "events/structured_events.jsonl")
        row = dict(event)
        index = _get_index()
        existing = index.rows(path, limit=1, where="event_id=?", params=(event["id"],))
        if existing:
            row = dict(existing[0][1])
            row.setdefault("sequence", existing[0][0])
        else:
            row["sequence"] = index.count(path)
        appended = _append_once(path, row)
        if event["category"] == "METRIC":
            # Repair a metrics write interrupted after structured persistence.
            _append_once(storage.result_file(event["task_id"], "events/metrics.jsonl"), row)
        return appended


def persist_many(events):
    return sum(1 for event in events if persist_structured_event(event))
