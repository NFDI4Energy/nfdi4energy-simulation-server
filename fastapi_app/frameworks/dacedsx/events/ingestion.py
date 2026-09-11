"""Kafka message durability boundary, independent of the consumer connection."""
import json
from fastapi_app.frameworks.dacedsx.events.persistence import append_dead_letter, persist_structured_event, validate_event


def process_message(msg):
    raw = msg.value()
    try:
        if raw is None:
            raise ValueError("empty Kafka message")
        event = json.loads(raw)
    except (ValueError, UnicodeDecodeError, TypeError) as exc:
        sample = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        append_dead_letter(str(exc), sample)
        return False
    valid, reason = validate_event(event)
    if not valid:
        append_dead_letter(reason, event, event.get("task_id") if isinstance(event, dict) else None)
        return False
    return persist_structured_event(event)


def persist_and_commit(consumer, message):
    persisted = process_message(message)
    consumer.commit(message=message, asynchronous=False)
    return persisted
