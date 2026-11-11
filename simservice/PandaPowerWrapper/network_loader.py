"""Load pandapower network files without executing code from them.

Network files reach the wrapper as scenario resources and may come from
other parties. Two of the formats pandapower reads can run code while
loading:

* pickle executes arbitrary code by design, so ``.p`` files are refused
  unless the operator sets ``PANDAPOWER_ALLOW_PICKLE=true`` for a trusted
  deployment;
* pandapower's own JSON tags objects with ``_module``/``_class`` and
  imports those modules while decoding, so such files are decoded only
  when every tag names a class pandapower needs for a plain network.

The simple dict format handled by ``pandapowerAPI.build_network`` and
Excel files carry no code and load as before.
"""
import json
import os
from pathlib import Path

import pandapower as pp

ALLOW_PICKLE_ENV = "PANDAPOWER_ALLOW_PICKLE"

# (module, class) pairs that pandapower.to_json writes for a plain network.
# Extend deliberately; anything else is refused before pandapower sees it.
ALLOWED_JSON_CLASSES = frozenset({
    ("pandapower.auxiliary", "pandapowerNet"),
    ("pandas.core.frame", "DataFrame"),
    ("pandas.core.series", "Series"),
})


class UnsafeNetworkError(ValueError):
    """The network file could execute code while loading."""


def pickle_allowed(allow_pickle=None):
    if allow_pickle is None:
        return os.environ.get(ALLOW_PICKLE_ENV, "false").strip().lower() == "true"
    return bool(allow_pickle)


def is_pandapower_json(data):
    """pandapower.to_json output starts with a tagged pandapowerNet object."""
    return isinstance(data, dict) and "_module" in data


def find_disallowed_classes(node):
    """Return the (module, class) tags in a JSON document that are not allowed.

    pandapower nests DataFrames as JSON strings inside the outer document,
    so strings that look like JSON are parsed and searched as well.
    """
    found = []
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if "_module" in current or "_class" in current:
                tag = (current.get("_module"), current.get("_class"))
                if tag not in ALLOWED_JSON_CLASSES and tag not in found:
                    found.append(tag)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, str) and current.lstrip()[:1] in ("{", "["):
            try:
                stack.append(json.loads(current))
            except ValueError:
                pass
    return found


def load_network(path, build_plain, allow_pickle=None):
    """Load a network from ``path``; ``build_plain`` turns the dict format into a net."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Network not found: {path}")

    ext = p.suffix.lower()
    if ext == ".json":
        with open(p, 'r') as f:
            data = json.load(f)
        if not is_pandapower_json(data):
            return build_plain(data)
        disallowed = find_disallowed_classes(data)
        if disallowed:
            tags = ", ".join(f"{module}.{cls}" for module, cls in disallowed)
            raise UnsafeNetworkError(
                f"Refusing {p.name}: it references classes pandapower would import while "
                f"loading ({tags}). Only plain pandapower networks are accepted.")
        return pp.from_json(str(p))
    if ext in (".xlsx", ".xls"):
        return pp.from_excel(str(p))
    if ext == ".p":
        if not pickle_allowed(allow_pickle):
            raise UnsafeNetworkError(
                f"Refusing {p.name}: unpickling executes code from the file. Convert it with "
                f"pandapower.to_json(net, '{p.stem}.json') or set {ALLOW_PICKLE_ENV}=true "
                f"for networks you trust.")
        return pp.from_pickle(str(p))
    raise RuntimeError(f"Unsupported format: {ext}")
