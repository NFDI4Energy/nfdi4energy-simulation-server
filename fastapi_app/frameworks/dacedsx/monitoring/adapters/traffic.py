"""SUMO topology parsing and projection, independent of HTTP or task state."""
import xml.etree.ElementTree as ET
from functools import lru_cache
from typing import Any, List
from fastapi_app.frameworks.dacedsx.events.normalization import safe_float

def parse_sumo_shape(shape: Any) -> List[List[float]]:
    if not isinstance(shape, str):
        return []
    points = []
    for raw_point in shape.split():
        coordinates = raw_point.split(",")
        if len(coordinates) < 2:
            continue
        x = safe_float(coordinates[0])
        y = safe_float(coordinates[1])
        if x is not None and y is not None:
            points.append([x, y])
    return points

@lru_cache(maxsize=16)
def _roads(path, signature):
    root = ET.parse(path).getroot()
    roads = []
    for edge in root.iter():
        if edge.tag.rsplit("}", 1)[-1] != "edge":
            continue
        edge_id = edge.get("id", "")
        if not edge_id or edge_id.startswith(":") or edge.get("function") == "internal":
            continue
        points = parse_sumo_shape(edge.get("shape"))
        if not points:
            for lane in edge:
                if lane.tag.rsplit("}", 1)[-1] == "lane":
                    points = parse_sumo_shape(lane.get("shape"))
                    if points:
                        break
        if len(points) >= 2:
            roads.append({"id": edge_id, "points": points})
    return roads


def load_roads(path):
    if path is None or not path.is_file():
        return []
    stat = path.stat()
    return _roads(str(path), (stat.st_ino, stat.st_size, stat.st_mtime_ns))


def projection(roads, entities, fallback_bounds=None):
    points = [p for road in roads for p in road["points"]]
    if points:
        xs, ys = zip(*points)
        bounds = (min(xs), min(ys), max(xs), max(ys))
    else:
        bounds = fallback_bounds
    def project(x, y):
        x, y = safe_float(x), safe_float(y)
        if x is None or y is None or bounds is None:
            return None
        left, bottom, right, top = bounds
        # Uniform scaling preserves the network's relative distances.
        span = max(right - left, top - bottom, 1)
        return [round(50 + 90 * (x - (left + right) / 2) / span, 4),
                round(50 - 90 * (y - (bottom + top) / 2) / span, 4)]
    projected_roads = [{"id": road["id"], "points": [project(*p) for p in road["points"]]} for road in roads]
    projected_entities = []
    for entity in entities if isinstance(entities, list) else []:
        if not isinstance(entity, dict) or not isinstance(entity.get("id"), (str, int)):
            continue
        point = project(entity.get("x"), entity.get("y"))
        if point:
            projected_entities.append({**entity, "id": str(entity["id"]), "x": point[0], "y": point[1]})
    return {"nodes": [], "edges": [], "roads": projected_roads}, projected_entities
