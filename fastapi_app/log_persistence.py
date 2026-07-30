import json
import os
from datetime import datetime, timezone
from typing import Iterable, List, Tuple


RESULTS_DIR = os.environ.get("RESULTS_DIR", "/data/results")
SUPPORTED_SCHEMA_VERSIONS = {"1.0"}

REQUIRED_EVENT_FIELDS = {
    "id",
    "schema_version",
    "task_id",
    "timestamp",
    "source",
    "category",
    "component",
    "event_code",
    "message",
}

VALID_CATEGORIES = {
    "PROGRESS",
    "VALIDATION",
    "WRAPPER",
    "SIMULATION",
    "METRIC",
    "WARNING",
    "ERROR",
    "RESULT",
}


def task_results_dir(task_id: str) -> str:
    return os.path.join(RESULTS_DIR, task_id)


def read_jsonl(path: str) -> List[dict]:
    if not os.path.isfile(path):
        return []

    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def validate_event(event: dict) -> Tuple[bool, str]:
    if not isinstance(event, dict):
        return False, "event must be a JSON object"

    missing = sorted(field for field in REQUIRED_EVENT_FIELDS if not event.get(field))
    if missing:
        return False, f"missing required fields: {', '.join(missing)}"

    if str(event.get("schema_version")) not in SUPPORTED_SCHEMA_VERSIONS:
        return False, f"unsupported schema_version: {event.get('schema_version')}"

    if event.get("category") not in VALID_CATEGORIES:
        return False, f"invalid category: {event.get('category')}"

    return True, ""


def append_jsonl_once(path: str, row: dict, id_field: str = "id") -> bool:
    parent = os.path.dirname(path)
    os.makedirs(parent, mode=0o777, exist_ok=True)
    os.chmod(parent, 0o777)
    row_id = row.get(id_field)

    if row_id and os.path.isfile(path):
        for existing in read_jsonl(path):
            if existing.get(id_field) == row_id:
                return False

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")
    os.chmod(path, 0o666)
    return True


def next_jsonl_sequence(path: str) -> int:
    return len(read_jsonl(path))


def append_dead_letter(reason: str, original_event, task_id: str = None):
    target_task = task_id or "unknown"
    debug_dir = os.path.join(task_results_dir(target_task), "debug")
    event_id = original_event.get("id") if isinstance(original_event, dict) else None
    row = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "error": reason,
        "event_id": event_id,
        "schema_version": original_event.get("schema_version") if isinstance(original_event, dict) else None,
        "original_event": original_event,
    }
    append_jsonl_once(
        os.path.join(debug_dir, "failed_event_samples.jsonl"),
        row,
        id_field="received_at",
    )


def persist_structured_event(event: dict) -> bool:
    valid, reason = validate_event(event)
    task_id = event.get("task_id") if isinstance(event, dict) else None
    if not valid:
        append_dead_letter(reason, event, task_id)
        return False

    events_dir = os.path.join(task_results_dir(event["task_id"]), "events")
    structured_path = os.path.join(events_dir, "structured_events.jsonl")
    event = dict(event)
    event.setdefault("sequence", next_jsonl_sequence(structured_path))
    appended = append_jsonl_once(
        structured_path,
        event,
    )

    if event.get("category") == "METRIC":
        append_jsonl_once(os.path.join(events_dir, "metrics.jsonl"), event)

    return appended


def persist_many(events: Iterable[dict]) -> int:
    return sum(1 for event in events if persist_structured_event(event))


def status_from_event(event: dict):
    category = event.get("category")
    event_code = event.get("event_code")
    metadata = event.get("metadata") or {}

    if event_code == "TASK_COMPLETED":
        return "DONE", ""
    if event_code == "TASK_FAILED":
        return "ERROR", event.get("message", "")
    if category == "ERROR" and metadata.get("fatal") is True:
        return "ERROR", event.get("message", "")
    if event_code in {"TASK_STARTED", "SIMULATION_STARTED", "STEP_COMPLETED"}:
        return "RUNNING", ""
    if event_code in {"TASK_ACCEPTED", "TASK_QUEUED"}:
        return "PENDING", ""

    return None, None
