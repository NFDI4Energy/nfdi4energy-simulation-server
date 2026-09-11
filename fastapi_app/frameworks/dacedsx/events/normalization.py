"""Pure event normalization used by adapters and the disposable event index."""
import math

TIME_SCALES = {"s": 1.0, "ms": 0.001, "us": 0.000001, "min": 60.0, "h": 3600.0}


def safe_float(value):
    if value is None or value == "":
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def safe_int(value):
    value = safe_float(value)
    return int(value) if value is not None and value.is_integer() else None


def event_metadata(event):
    value = event.get("metadata")
    return value if isinstance(value, dict) else {}


def event_domain(event):
    domain = event_metadata(event).get("domain")
    if isinstance(domain, str) and domain in {"energy", "traffic"}:
        return domain
    component = str(event.get("component", "")).lower()
    if "sumo" in component:
        return "traffic"
    if "panda" in component:
        return "energy"
    return None


def event_instance(event):
    metadata = event_metadata(event)
    value = event.get("instance_id") or metadata.get("instance_id") or metadata.get("instanceID") or metadata.get("wrapper_id")
    return str(value) if isinstance(value, (str, int)) else None


def event_time_seconds(event, domain=None):
    value = safe_float(event.get("simulation_time"))
    if value is None:
        return None
    unit = event_metadata(event).get("simulation_time_unit")
    if unit is None:
        return value / 1000 if (domain or event_domain(event)) == "traffic" else value
    return value * TIME_SCALES[unit] if isinstance(unit, str) and unit in TIME_SCALES else None

