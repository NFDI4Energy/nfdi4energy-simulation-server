"""Pandapower file adaptation and topology, independent of FastAPI."""
import json
from typing import Any, Dict, List
from fastapi_app.frameworks.dacedsx.events.normalization import safe_float, safe_int


def network_object(value):
    if not isinstance(value, dict):
        return {}
    value = value.get("_object", value)
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def dataframe_split_rows(value: Any) -> List[dict]:
    if not isinstance(value, dict):
        return []
    if value.get("_class") != "DataFrame":
        return []

    payload = value.get("_object")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return []
    if not isinstance(payload, dict):
        return []

    columns = payload.get("columns", [])
    indexes = payload.get("index", [])
    data = payload.get("data", [])
    rows = []
    for offset, raw_row in enumerate(data):
        if not isinstance(raw_row, list):
            continue
        row = {column: raw_row[index] if index < len(raw_row) else None for index, column in enumerate(columns)}
        row["__index"] = indexes[offset] if offset < len(indexes) else offset
        rows.append(row)
    return rows


def network_table(network: Dict[str, Any], name: str) -> List[dict]:
    value = network.get(name)
    if isinstance(value, list):
        rows = []
        for index, row in enumerate(value):
            if isinstance(row, dict):
                rows.append({"__index": index, **row})
        return rows
    return dataframe_split_rows(value)

def layout_buses(bus_ids: List[str], edges: List[dict]) -> Dict[str, Dict[str, float]]:
    if not bus_ids:
        return {}
    if len(bus_ids) == 1:
        return {bus_ids[0]: {"x": 50.0, "y": 50.0}}

    adjacency = {bus_id: set() for bus_id in bus_ids}
    for edge in edges:
        if edge["from"] in adjacency and edge["to"] in adjacency:
            adjacency[edge["from"]].add(edge["to"])
            adjacency[edge["to"]].add(edge["from"])

    root = bus_ids[0]
    depths = {root: 0}
    queue = [root]
    while queue:
        current = queue.pop(0)
        for neighbor in sorted(adjacency[current]):
            if neighbor in depths:
                continue
            depths[neighbor] = depths[current] + 1
            queue.append(neighbor)

    next_depth = max(depths.values(), default=0) + 1
    for bus_id in bus_ids:
        if bus_id not in depths:
            depths[bus_id] = next_depth
            next_depth += 1

    by_depth = {}
    for bus_id, depth in depths.items():
        by_depth.setdefault(depth, []).append(bus_id)

    max_depth = max(by_depth.keys(), default=0)
    layout = {}
    for depth, level_ids in by_depth.items():
        level_ids = sorted(level_ids)
        x = 50.0 if max_depth == 0 else 12.0 + (76.0 * depth / max_depth)
        if len(level_ids) == 1:
            y_values = [50.0]
        else:
            y_values = [18.0 + (64.0 * index / (len(level_ids) - 1)) for index in range(len(level_ids))]
        for bus_id, y in zip(level_ids, y_values):
            layout[bus_id] = {"x": round(x, 2), "y": round(y, 2)}
    return layout


def build_pandapower_network(network, bus_values, line_loading_values) -> Dict[str, List[dict]]:
    if not network:
        return {"nodes": [], "edges": [], "roads": []}

    buses = network_table(network, "bus")
    lines = network_table(network, "line")
    trafos = network_table(network, "trafo")

    bus_id_by_index = {}
    for offset, bus in enumerate(buses):
        raw_index = bus.get("__index", offset)
        bus_id_by_index[str(raw_index)] = f"bus_{raw_index}"

    edges = []
    for offset, line in enumerate(lines):
        line_index = line.get("__index", offset)
        from_bus = safe_int(line.get("from_bus"))
        to_bus = safe_int(line.get("to_bus"))
        if from_bus is None or to_bus is None:
            continue
        edges.append(
            {
                "id": f"line_{line_index}",
                "kind": "line",
                "label": str(line.get("name") or f"Line {line_index}"),
                "from": bus_id_by_index.get(str(from_bus), f"bus_{from_bus}"),
                "to": bus_id_by_index.get(str(to_bus), f"bus_{to_bus}"),
                "loading": safe_float(line_loading_values.get(f"line_{line_index}")),
            }
        )

    for offset, trafo in enumerate(trafos):
        trafo_index = trafo.get("__index", offset)
        hv_bus = safe_int(trafo.get("hv_bus"))
        lv_bus = safe_int(trafo.get("lv_bus"))
        if hv_bus is None or lv_bus is None:
            continue
        edges.append(
            {
                "id": f"trafo_{trafo_index}",
                "kind": "trafo",
                "label": str(trafo.get("name") or f"Trafo {trafo_index}"),
                "from": bus_id_by_index.get(str(hv_bus), f"bus_{hv_bus}"),
                "to": bus_id_by_index.get(str(lv_bus), f"bus_{lv_bus}"),
                "loading": None,
            }
        )

    bus_ids = [bus_id_by_index[str(bus.get("__index", offset))] for offset, bus in enumerate(buses)]
    layout = layout_buses(bus_ids, edges)
    nodes = []
    for offset, bus in enumerate(buses):
        raw_index = bus.get("__index", offset)
        bus_id = f"bus_{raw_index}"
        label = bus.get("name") or f"Bus {raw_index}"
        voltage = safe_float(bus_values.get(str(label), bus_values.get(f"bus_{raw_index}")))
        position = layout.get(bus_id, {"x": 50.0, "y": 50.0})
        nodes.append(
            {
                "id": bus_id,
                "label": str(label),
                "x": position["x"],
                "y": position["y"],
                "voltage": voltage,
            }
        )

    return {"nodes": nodes, "edges": edges, "roads": []}
