import os
import json
import uuid
import mimetypes
import csv
import math
import asyncio
import xml.etree.ElementTree as ET
from functools import lru_cache
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from models import Scenario
from pydantic import ValidationError
import redis
from fastapi import FastAPI, Request, UploadFile, File, Depends
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from rabbitmq_client import SimulationQueue
from database import init_db, get_db
from auth import router as auth_router, require_login, get_current_user_or_none
from log_persistence import persist_structured_event, status_from_event
from models_db import User, Task


REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
RESULTS_DIR = os.environ.get("RESULTS_DIR", "/data/results")
RESOURCES_DIR = os.environ.get("RESOURCES_DIR", "/data/resources")
SESSION_SECRET = os.environ.get("SESSION_SECRET")
if not SESSION_SECRET:
    raise RuntimeError("SESSION_SECRET must be configured")

redis_client = redis.Redis(host=REDIS_HOST, port=6379, db=0)

app = FastAPI()


app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Mount the /auth/* endpoints (login, callback, logout, me)
app.include_router(auth_router)

SERVER_ROOT = os.path.dirname(__file__)

app.mount(
    "/static", StaticFiles(directory=os.path.join(SERVER_ROOT, "static")), name="static"
)

app.mount(
    "/dashboard", StaticFiles(directory=os.path.join(SERVER_ROOT, "static/svelte-dist"), html=True), name="dashboard"
)

templates = Jinja2Templates(directory=os.path.join(SERVER_ROOT, "templates"))


def task_input_dir(task_id: str) -> str:
    return os.path.join(RESOURCES_DIR, task_id)


def task_results_dir(task_id: str) -> str:
    return os.path.join(RESULTS_DIR, task_id)


ENERGY_OBSERVABLES = [
    {"key": "bus.vm_pu.min", "label": "Min voltage", "unit": "p.u.", "default": True, "visualization": "card"},
    {"key": "bus.vm_pu.max", "label": "Max voltage", "unit": "p.u.", "default": True, "visualization": "card"},
    {"key": "line.loading_percent.max", "label": "Max line loading", "unit": "%", "default": True, "visualization": "card"},
    {"key": "load.p_mw.total", "label": "Total load", "unit": "MW", "default": True, "visualization": "line"},
]

TRAFFIC_OBSERVABLES = [
    {"key": "vehicles.active", "label": "Active vehicles", "unit": "", "default": True, "visualization": "card"},
    {"key": "speed.avg_mps", "label": "Average speed", "unit": "m/s", "default": True, "visualization": "card"},
    {"key": "vehicles.arrived", "label": "Arrived", "unit": "", "default": True, "visualization": "line"},
]


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


def event_level(event: dict) -> str:
    category = event.get("category", "PROGRESS")
    if category == "ERROR":
        return "error"
    if category == "WARNING":
        return "warning"
    return "info"


def latest_progress(events: List[dict], status: str) -> float:
    for event in reversed(events):
        progress = event.get("progress")
        if isinstance(progress, (int, float)):
            return max(0.0, min(1.0, float(progress)))
    if status == "DONE":
        return 1.0
    if status == "ERROR":
        return 1.0
    if status == "RUNNING":
        return 0.2
    return 0.0


def safe_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def safe_int(value: Any) -> Optional[int]:
    numeric = safe_float(value)
    if numeric is None:
        return None
    return int(numeric)


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


def load_network_resource(task_id: str) -> Optional[Dict[str, Any]]:
    resources_dir = task_input_dir(task_id)
    if not os.path.isdir(resources_dir):
        return None

    for root, _, filenames in os.walk(resources_dir):
        for filename in sorted(filenames):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(root, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    candidate = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue

            network = candidate.get("_object", candidate) if isinstance(candidate, dict) else None
            if not isinstance(network, dict):
                continue
            if network_table(network, "bus") and (network_table(network, "line") or network_table(network, "trafo")):
                return network
    return None


def latest_csv_row(path: str) -> Dict[str, Any]:
    return csv_row_at(path)


def csv_row_at(path: str, index: Optional[int] = None) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    rows = []
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                rows.append(row)
    except OSError:
        return {}
    if not rows:
        return {}
    if index is None:
        return rows[-1]
    clamped = max(0, min(index, len(rows) - 1))
    return rows[clamped]


def csv_row_count(path: str) -> int:
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return sum(1 for _ in csv.DictReader(f))
    except OSError:
        return 0


def clamp_index(index: Optional[int], count: int) -> Optional[int]:
    if count <= 0:
        return None
    if index is None:
        return count - 1
    return max(0, min(index, count - 1))


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


def build_pandapower_network(task_id: str, history_index: Optional[int] = None) -> Dict[str, List[dict]]:
    network = load_network_resource(task_id)
    if not network:
        return {"nodes": [], "edges": [], "roads": []}

    buses = network_table(network, "bus")
    lines = network_table(network, "line")
    trafos = network_table(network, "trafo")
    bus_values = csv_row_at(os.path.join(task_results_dir(task_id), "bus_vm_pu.csv"), history_index)
    line_loading_values = csv_row_at(os.path.join(task_results_dir(task_id), "line_loading_percent.csv"), history_index)

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
        voltage = safe_float(bus_values.get(str(label)))
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


@lru_cache(maxsize=64)
def _load_sumo_roads(resources_root: str, task_id: str) -> tuple:
    resources_dir = os.path.join(resources_root, task_id)
    if not os.path.isdir(resources_dir):
        return ()

    for root, _, filenames in os.walk(resources_dir):
        for filename in sorted(filenames):
            if not filename.endswith(".net.xml"):
                continue
            try:
                network_root = ET.parse(os.path.join(root, filename)).getroot()
            except (OSError, ET.ParseError):
                continue

            roads = []
            for edge in network_root.iter():
                if edge.tag.rsplit("}", 1)[-1] != "edge":
                    continue
                edge_id = edge.get("id", "")
                if not edge_id or edge_id.startswith(":") or edge.get("function") == "internal":
                    continue

                points = parse_sumo_shape(edge.get("shape"))
                if not points:
                    for child in edge:
                        if child.tag.rsplit("}", 1)[-1] == "lane":
                            points = parse_sumo_shape(child.get("shape"))
                            if points:
                                break
                if len(points) >= 2:
                    roads.append({"id": edge_id, "points": points})
            if roads:
                return tuple((road["id"], tuple(tuple(point) for point in road["points"])) for road in roads)
    return ()


def load_sumo_roads(task_id: str) -> List[dict]:
    return [
        {"id": road_id, "points": [list(point) for point in points]}
        for road_id, points in _load_sumo_roads(RESOURCES_DIR, task_id)
    ]


def traffic_bounds(roads: List[dict], metric_events: List[dict]) -> Optional[tuple]:
    bounds = [math.inf, math.inf, -math.inf, -math.inf]

    def include(x: Any, y: Any):
        numeric_x = safe_float(x)
        numeric_y = safe_float(y)
        if numeric_x is None or numeric_y is None:
            return
        bounds[0] = min(bounds[0], numeric_x)
        bounds[1] = min(bounds[1], numeric_y)
        bounds[2] = max(bounds[2], numeric_x)
        bounds[3] = max(bounds[3], numeric_y)

    for road in roads:
        for point in road.get("points", []):
            if isinstance(point, list) and len(point) >= 2:
                include(point[0], point[1])

    # A SUMO network normally establishes stable bounds. This fallback keeps
    # history playback stable when only vehicle telemetry is available.
    if not roads:
        for event in metric_events:
            for entity in event_metadata(event).get("entities", []):
                if isinstance(entity, dict):
                    include(entity.get("x"), entity.get("y"))

    if math.isinf(bounds[0]):
        return None
    return tuple(bounds)


def project_traffic_point(x: Any, y: Any, bounds: Optional[tuple]) -> Optional[List[float]]:
    numeric_x = safe_float(x)
    numeric_y = safe_float(y)
    if numeric_x is None or numeric_y is None or bounds is None:
        return None
    min_x, min_y, max_x, max_y = bounds
    projected_x = 50.0 if max_x == min_x else 5.0 + 90.0 * (numeric_x - min_x) / (max_x - min_x)
    projected_y = 50.0 if max_y == min_y else 95.0 - 90.0 * (numeric_y - min_y) / (max_y - min_y)
    return [round(max(0.0, min(100.0, projected_x)), 2), round(max(0.0, min(100.0, projected_y)), 2)]


def build_sumo_projection(task_id: str, metric_events: List[dict], selected_event: dict) -> tuple:
    raw_roads = load_sumo_roads(task_id)
    bounds = traffic_bounds(raw_roads, metric_events)
    roads = []
    for road in raw_roads:
        points = [project_traffic_point(point[0], point[1], bounds) for point in road["points"]]
        roads.append({"id": road["id"], "points": [point for point in points if point is not None]})

    entities = []
    raw_entities = event_metadata(selected_event).get("entities", [])
    if isinstance(raw_entities, list):
        for raw_entity in raw_entities:
            if not isinstance(raw_entity, dict):
                continue
            position = project_traffic_point(raw_entity.get("x"), raw_entity.get("y"), bounds)
            if position is None:
                continue
            entities.append({**raw_entity, "x": position[0], "y": position[1]})

    return {"nodes": [], "edges": [], "roads": roads}, entities


def task_scenario_domain(task_id: str) -> Optional[str]:
    resources_dir = task_input_dir(task_id)
    if not os.path.isdir(resources_dir):
        return None
    for filename in sorted(os.listdir(resources_dir)):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(resources_dir, filename), "r", encoding="utf-8") as source:
                candidate = json.load(source)
        except (OSError, json.JSONDecodeError):
            continue
        blocks = candidate.get("buildingBlocks") if isinstance(candidate, dict) else None
        if not isinstance(blocks, list):
            continue
        domains = [block.get("domain") for block in blocks if isinstance(block, dict)]
        if "traffic" in domains:
            return "traffic"
        if "energy" in domains:
            return "energy"
    return None


def monitor_domain(task_id: str, metric_events: List[dict], structured_events: List[dict]) -> str:
    for event in reversed(metric_events):
        domain = event_metadata(event).get("domain")
        if domain in {"energy", "traffic"}:
            return domain
    for event in reversed(structured_events):
        if str(event.get("component", "")).lower() == "sumowrapper":
            return "traffic"
    return task_scenario_domain(task_id) or "energy"


def event_metadata(event: dict) -> dict:
    metadata = event.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def event_time_seconds(event: dict, domain: Optional[str] = None) -> Any:
    value = event.get("simulation_time", 0)
    numeric = safe_float(value)
    if numeric is None:
        return value
    metadata = event_metadata(event)
    event_domain = domain or metadata.get("domain")
    if event_domain is None and str(event.get("component", "")).lower() == "sumowrapper":
        event_domain = "traffic"
    time_unit = metadata.get("simulation_time_unit")
    if time_unit == "ms" or (event_domain == "traffic" and time_unit != "s"):
        return numeric / 1000.0
    return numeric


def frontend_event(event: dict, domain: Optional[str] = None) -> dict:
    return {
        **event,
        "time": event_time_seconds(event, domain),
        "level": event_level(event),
        "source": event.get("component") or event.get("source") or "SimService",
    }


def sse_message(event_name: str, data: dict = None) -> str:
    lines = [f"event: {event_name}"]
    if data is not None:
        payload = json.dumps(data, separators=(",", ":"))
        for line in payload.splitlines() or [""]:
            lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def append_structured_event(task_id: str, event: dict):
    event_dir = os.path.join(task_results_dir(task_id), "events")
    os.makedirs(event_dir, exist_ok=True)
    with open(os.path.join(event_dir, "structured_events.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, separators=(",", ":")) + "\n")


def create_task_event(task_id: str, category: str, component: str, event_code: str, message: str, progress: float = None):
    event = {
        "id": f"evt_{uuid.uuid4()}",
        "schema_version": "1.0",
        "task_id": task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "web",
        "category": category,
        "component": component,
        "event_code": event_code,
        "message": message,
    }
    if progress is not None:
        event["progress"] = progress
    persist_structured_event(event)


# ---------------------------------------------------------------------------
# Startup: initialise the database tables
# ---------------------------------------------------------------------------

@app.on_event("startup")
def on_startup():
    init_db()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_or_none(request, db)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
        },
    )



@app.post("/submit")
async def submit_simulation(
    request: Request,
    scenario_file: UploadFile = File(...),
    resource_files: List[UploadFile] = File(default=[]),
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):

    # 1. Read and validate scenario
    content = await scenario_file.read()
    try:
        scenario_dict = json.loads(content)
        scenario = Scenario(**scenario_dict)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON mapping in scenario file"})
    except ValidationError as e:
        return JSONResponse(status_code=400, content={"error": f"Scenario validation failed: {e.errors()}"})

    # 1a. Validate required resource files
    required_files = set()
    for bb in scenario.buildingBlocks:
        if bb.resources:
            required_files.update(bb.resources.keys())

    provided_files = {f.filename for f in resource_files if f.filename}
    missing_files = required_files - provided_files

    if missing_files:
        return JSONResponse(
            status_code=400,
            content={"error": f"Missing required resource files listed in scenario: {', '.join(missing_files)}"},
        )

    # 2. Setup task directory
    task_id = str(uuid.uuid4())
    task_resources_dir = task_input_dir(task_id)
    task_results_path = task_results_dir(task_id)
    os.makedirs(task_resources_dir, mode=0o777, exist_ok=True)
    os.makedirs(task_results_path, mode=0o777, exist_ok=True)
    os.chmod(task_resources_dir, 0o777)
    os.chmod(task_results_path, 0o777)
    create_task_event(task_id, "PROGRESS", "WebService", "TASK_ACCEPTED", "Simulation task accepted", 0.01)

    # 3. Save scenario file
    with open(os.path.join(task_resources_dir, scenario_file.filename), "wb") as out:
        out.write(content)

    # 4. Save resource files
    for f in resource_files:
        if f.filename:
            res_content = await f.read()
            with open(os.path.join(task_resources_dir, f.filename), "wb") as out:
                out.write(res_content)
    create_task_event(task_id, "VALIDATION", "WebService", "SCENARIO_VALIDATED", "Scenario and resource files validated", 0.05)

    # 5. Queue task
    queue = SimulationQueue()
    queue.publish(task_id, scenario_dict)
    queue.close()
    create_task_event(task_id, "PROGRESS", "WebService", "TASK_QUEUED", "Simulation task queued", 0.08)

    redis_client.hset(
        f"task:{task_id}",
        mapping={"status": "PENDING", "files": "[]", "error": ""},
    )

    # 6. Save task in PostgreSQL, linked to the current user
    all_filenames = [scenario_file.filename] + [f.filename for f in resource_files if f.filename]
    db_task = Task(
        id=task_id,
        user_id=current_user.id,
        scenario_id=scenario_dict.get("scenarioID"),
        resource_files=all_filenames,
    )
    db.add(db_task)
    db.commit()

    return JSONResponse(content={"task_id": task_id})


@app.get("/check/{task_id}")
async def check_task(
    task_id: str,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    # Verify task ownership
    db_task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if db_task is None:
        return JSONResponse(content={"error": "Task not found or access denied"}, status_code=404)

    runtime = resolved_task_status(task_id, db_task.status or "PENDING")
    status = runtime["status"]
    response = {"task_id": task_id, "status": status}

    if status == "DONE":
        # Scan actual results directory for files
        task_dir = task_results_dir(task_id)
        files = []
        if os.path.isdir(task_dir):
            for root, _, filenames in os.walk(task_dir):
                for f in filenames:
                    rel = os.path.relpath(os.path.join(root, f), task_dir)
                    files.append(rel)
        response["files"] = files
        response["downloads"] = [f"/download/{task_id}/{f}" for f in files]
    elif status == "ERROR":
        response["error"] = runtime["error"]

    return JSONResponse(content=response)


@app.get("/list_files/{task_id}")
async def list_files(
    task_id: str,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    # Verify task ownership
    db_task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if db_task is None:
        return JSONResponse(content={"error": "Task not found or access denied"}, status_code=404)

    task_dir = task_results_dir(task_id)

    if not os.path.isdir(task_dir):
        return JSONResponse(
            content={"error": "No results directory found"}, status_code=404
        )

    files = []
    for root, _, filenames in os.walk(task_dir):
        for f in filenames:
            rel = os.path.relpath(os.path.join(root, f), task_dir)
            files.append(rel)

    return JSONResponse(content={"task_id": task_id, "files": files})


@app.get("/monitor/{task_id}/events")
async def monitor_events(
    task_id: str,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    db_task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if db_task is None:
        return JSONResponse(content={"error": "Task not found or access denied"}, status_code=404)

    events_path = os.path.join(task_results_dir(task_id), "events", "structured_events.jsonl")
    return JSONResponse(content={"task_id": task_id, "events": read_jsonl(events_path)})


@app.get("/monitor/{task_id}/metrics")
async def monitor_metrics(
    task_id: str,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    db_task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if db_task is None:
        return JSONResponse(content={"error": "Task not found or access denied"}, status_code=404)

    metrics_path = os.path.join(task_results_dir(task_id), "events", "metrics.jsonl")
    return JSONResponse(content={"task_id": task_id, "metrics": read_jsonl(metrics_path)})


@app.get("/monitor/{task_id}/debug/failed-events")
async def monitor_failed_events(
    task_id: str,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    db_task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if db_task is None:
        return JSONResponse(content={"error": "Task not found or access denied"}, status_code=404)

    failed_events_path = os.path.join(task_results_dir(task_id), "debug", "failed_event_samples.jsonl")
    failed_events = read_jsonl(failed_events_path)
    return JSONResponse(
        content={
            "task_id": task_id,
            "failedEvents": failed_events[-80:],
            "count": len(failed_events),
        }
    )


def task_runtime_status(task_id: str) -> Dict[str, Any]:
    try:
        redis_data = redis_client.hgetall(f"task:{task_id}")
    except redis.RedisError:
        redis_data = {}
    status = redis_data.get(b"status", b"PENDING").decode() if redis_data else "PENDING"
    error = redis_data.get(b"error", b"").decode() if redis_data else ""
    return {"status": status, "error": error, "redis_found": bool(redis_data)}


def reconcile_runtime_status(runtime: Dict[str, Any], events: List[dict]) -> Dict[str, Any]:
    """Fold durable lifecycle events over Redis, which may lag after a worker restart."""
    reconciled = dict(runtime)
    for event in events:
        status, error = status_from_event(event)
        if status:
            reconciled["status"] = status
            reconciled["error"] = error or ""
    return reconciled


def has_legacy_result_artifacts(task_id: str) -> bool:
    """Recognize completed runs created before structured terminal events existed."""
    results_dir = task_results_dir(task_id)
    if not os.path.isdir(results_dir):
        return False

    ignored_directories = {"events", "debug", "logs"}
    for root, directories, filenames in os.walk(results_dir):
        relative_root = os.path.relpath(root, results_dir)
        if relative_root == ".":
            directories[:] = [name for name in directories if name not in ignored_directories]
        for filename in filenames:
            if filename == ".simservice-write-test":
                continue
            path = os.path.join(root, filename)
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                return True
    return False


def resolved_task_status(
    task_id: str,
    fallback_status: str = "PENDING",
    events: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    runtime = task_runtime_status(task_id)
    if not runtime.get("redis_found"):
        runtime["status"] = fallback_status or "PENDING"

    if events is None:
        events_path = os.path.join(task_results_dir(task_id), "events", "structured_events.jsonl")
        events = read_jsonl(events_path)
    resolved = reconcile_runtime_status(runtime, events)
    if resolved["status"] in {"PENDING", "UNKNOWN"} and has_legacy_result_artifacts(task_id):
        resolved["status"] = "DONE"
        resolved["error"] = ""

    if not runtime.get("redis_found") and resolved["status"] in {"DONE", "ERROR", "RUNNING"}:
        try:
            redis_client.hset(
                f"task:{task_id}",
                mapping={"status": resolved["status"], "error": resolved["error"], "files": "[]"},
            )
        except redis.RedisError:
            pass
    return resolved


def build_monitor_payload(task_id: str, cursor: int = 0, history_index: Optional[int] = None) -> dict:
    events_dir = os.path.join(task_results_dir(task_id), "events")
    structured_events = read_jsonl(os.path.join(events_dir, "structured_events.jsonl"))
    metric_events = read_jsonl(os.path.join(events_dir, "metrics.jsonl"))
    runtime = resolved_task_status(task_id, events=structured_events)
    status = runtime["status"]
    error = runtime["error"]
    domain = monitor_domain(task_id, metric_events, structured_events)

    playback_count = len(metric_events) or csv_row_count(os.path.join(task_results_dir(task_id), "bus_vm_pu.csv"))
    selected_metric_index = clamp_index(history_index, playback_count)
    latest_metric_event = metric_events[-1] if metric_events else {}
    selected_metric_event = metric_events[selected_metric_index] if metric_events and selected_metric_index is not None else latest_metric_event
    metrics = event_metadata(selected_metric_event).get("metrics", {})
    metric_history = [
        {
            "time": event_time_seconds(event, domain),
            "values": event_metadata(event).get("metrics", {}),
        }
        for index, event in enumerate(metric_events)
    ]

    latest_event = structured_events[-1] if structured_events else {}
    simulation_time_event = selected_metric_event if selected_metric_event.get("simulation_time") is not None else latest_event
    if simulation_time_event.get("simulation_time") is None and latest_metric_event:
        simulation_time_event = latest_metric_event
    simulation_time = event_time_seconds(simulation_time_event, domain)
    if simulation_time_event.get("simulation_time") is None and selected_metric_index is not None:
        simulation_time = selected_metric_index
    simulation_time = simulation_time or 0

    simulation_end = 0
    for event in reversed(structured_events):
        metadata = event_metadata(event)
        total_steps = metadata.get("total_steps")
        step = metadata.get("step")
        event_time = event_time_seconds(event, domain)
        if isinstance(total_steps, int) and isinstance(step, int) and step >= 0 and isinstance(event_time, (int, float)):
            step_length = event_time / step if step else event_time or 1
            simulation_end = total_steps * step_length
            break
    if not simulation_end:
        simulation_end = max(simulation_time, 1)

    visible_events = structured_events[cursor:] if cursor > 0 else structured_events[-80:]
    frontend_events = [frontend_event(event, domain) for event in visible_events]

    selected_metadata = event_metadata(selected_metric_event)
    selected_step = safe_int(selected_metadata.get("step"))
    selected_total_steps = safe_int(selected_metadata.get("total_steps"))
    selected_progress = selected_metric_event.get("progress")
    if domain == "traffic" and selected_step is not None and selected_total_steps:
        selected_progress = selected_step / selected_total_steps
    if selected_progress is None and playback_count > 1 and selected_metric_index is not None:
        selected_progress = selected_metric_index / (playback_count - 1)

    if domain == "traffic":
        network, entities = build_sumo_projection(task_id, metric_events, selected_metric_event)
        observables = TRAFFIC_OBSERVABLES
        title = "SUMO traffic run"
    else:
        network = build_pandapower_network(task_id, selected_metric_index)
        entities = []
        observables = ENERGY_OBSERVABLES
        title = "Simulation run"

    snapshot = {
        "taskId": task_id,
        "domain": domain,
        "title": title,
        "status": status,
        "simulationTime": simulation_time,
        "simulationStart": 0,
        "simulationEnd": simulation_end,
        "progress": selected_progress if selected_progress is not None else latest_progress(structured_events, status),
        "updatedAt": selected_metric_event.get("timestamp") or latest_event.get("timestamp") or latest_metric_event.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "error": error,
    }

    return {
        "cursor": len(structured_events),
        "snapshot": snapshot,
        "metrics": metrics,
        "metricHistory": metric_history[-80:],
        "entities": entities,
        "network": network,
        "events": frontend_events,
        "observables": observables,
        "playback": {
            "index": selected_metric_index if selected_metric_index is not None else 0,
            "count": playback_count,
            "isLatest": selected_metric_index is None or selected_metric_index == playback_count - 1,
        },
    }


@app.get("/monitor/{task_id}")
async def monitor_run(
    task_id: str,
    cursor: int = 0,
    history_index: Optional[int] = None,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    db_task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if db_task is None:
        return JSONResponse(content={"error": "Task not found or access denied"}, status_code=404)

    return JSONResponse(content=build_monitor_payload(task_id, cursor, history_index))


@app.get("/monitor/{task_id}/snapshot")
async def monitor_snapshot(
    task_id: str,
    cursor: int = 0,
    history_index: Optional[int] = None,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    db_task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if db_task is None:
        return JSONResponse(content={"error": "Task not found or access denied"}, status_code=404)

    return JSONResponse(content=build_monitor_payload(task_id, cursor, history_index))


@app.get("/monitor/{task_id}/stream")
async def monitor_stream(
    task_id: str,
    request: Request,
    cursor: int = 0,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    db_task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if db_task is None:
        return JSONResponse(content={"error": "Task not found or access denied"}, status_code=404)

    events_path = os.path.join(task_results_dir(task_id), "events", "structured_events.jsonl")

    async def stream_events():
        next_index = max(0, cursor)
        last_heartbeat = 0.0

        yield sse_message("ready", {"cursor": next_index})

        while True:
            if await request.is_disconnected():
                break

            events = read_jsonl(events_path)
            while next_index < len(events):
                event = events[next_index]
                next_index += 1
                yield sse_message(
                    "structured-event",
                    {
                        "cursor": next_index,
                        "event": frontend_event(event),
                    },
                )

            now = asyncio.get_running_loop().time()
            if now - last_heartbeat >= 15:
                last_heartbeat = now
                yield sse_message("heartbeat", {"cursor": next_index})

            await asyncio.sleep(1)

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/download/{task_id}/{filename:path}")
async def download_file(
    task_id: str,
    filename: str,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    # Verify task ownership
    db_task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if db_task is None:
        return JSONResponse(content={"error": "Task not found or access denied"}, status_code=404)

    file_path = os.path.join(task_results_dir(task_id), filename)

    if not os.path.isfile(file_path):
        return JSONResponse(content={"error": "File not found"}, status_code=404)

    media_type, _ = mimetypes.guess_type(filename)

    return FileResponse(
        path=file_path,
        filename=os.path.basename(filename),
        media_type=media_type or "application/octet-stream",
    )


# ---------------------------------------------------------------------------
# New endpoint: list all tasks for the current user
# ---------------------------------------------------------------------------

@app.get("/my-tasks")
async def my_tasks(
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Return all tasks belonging to the currently logged-in user."""
    tasks = (
        db.query(Task)
        .filter(Task.user_id == current_user.id)
        .order_by(Task.created_at.desc())
        .all()
    )

    result = []
    for t in tasks:
        runtime = resolved_task_status(t.id, t.status or "PENDING")

        result.append({
            "task_id": t.id,
            "scenario_id": t.scenario_id,
            "status": runtime["status"],
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    return JSONResponse(content={"tasks": result})
