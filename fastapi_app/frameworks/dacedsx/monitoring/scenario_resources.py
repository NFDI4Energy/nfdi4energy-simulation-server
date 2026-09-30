import json
from functools import lru_cache
from fastapi_app.frameworks.dacedsx.monitoring.adapters.energy import network_table, network_object


@lru_cache(maxsize=16)
def _json(path, signature):
    with open(path, encoding="utf-8") as source:
        return json.load(source)


def load_json(path):
    stat = path.stat()
    return _json(str(path), (stat.st_ino, stat.st_size, stat.st_mtime_ns))


def scenario_stream(storage, task_id, filenames=None):
    warnings = []
    root = storage.inputs(task_id)
    candidates = []
    names = filenames[:1] if isinstance(filenames, list) and filenames else sorted(p.name for p in root.glob("*.json"))
    for name in names:
        try:
            candidate = load_json(storage.input_file(task_id, name))
        except (OSError, ValueError):
            continue
        if isinstance(candidate, dict) and isinstance(candidate.get("buildingBlocks"), list):
            candidates.append(candidate)
    if len(candidates) > 1:
        return {}, {}, ["Multiple scenario files; stream cannot be resolved"]
    scenario = candidates[0] if candidates else {}
    supported = [b for b in scenario.get("buildingBlocks", []) if isinstance(b, dict) and
                 b.get("domain") in ("energy", "traffic")]
    block = supported[0] if supported else {}
    if len(supported) > 1:
        warnings.append("Only the first supported building block is displayed")
    return scenario, block, warnings


def network_resource(storage, task_id, block, domain):
    declared = block.get("resources") or {}
    if not isinstance(declared, dict):
        return None, ["Invalid network resource declarations"]
    matches = [name for name, kind in declared.items()
               if (domain == "energy" and str(kind).lower() == "network") or
                  (domain == "traffic" and (str(kind).lower() == "roadmap" or name.endswith(".net.xml")))]
    if len(matches) == 1:
        path = storage.input_file(task_id, matches[0])
        return (path, []) if path.is_file() else (None, ["Declared network resource is missing"])
    if len(matches) > 1:
        return None, ["Multiple declared network resources"]
    # Legacy discovery must establish a unique match, never take the first file.
    matches = []
    root = storage.inputs(task_id)
    for candidate in root.rglob("*.net.xml" if domain == "traffic" else "*.json"):
        try:
            candidate = storage.input_file(task_id, str(candidate.relative_to(root)))
            if domain == "energy":
                value = network_object(load_json(candidate))
                if not isinstance(value, dict) or not network_table(value, "bus"):
                    continue
            matches.append(candidate)
        except (OSError, ValueError, TypeError):
            continue
    if len(matches) == 1:
        return matches[0], ["Network resource inferred from legacy files"]
    return None, ["Network resource is ambiguous" if matches else "Network resource is unavailable"]
