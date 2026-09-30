"""Frontend event representation, independent of persistence and indexing."""
from fastapi_app.frameworks.dacedsx.events.normalization import event_time_seconds


def frontend_event(event, domain=None):
    category = event.get("category")
    return {**event, "time": event_time_seconds(event, domain),
            "level": {"ERROR": "error", "WARNING": "warning"}.get(category, "info"),
            "source": event.get("source") or event.get("component") or "SimService"}
