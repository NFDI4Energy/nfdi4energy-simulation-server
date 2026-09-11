from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Snapshot(BaseModel):
    taskId: str
    domain: str
    title: str
    status: str
    error: str = ""
    statusSource: str
    redisAvailable: bool
    simulationTime: Optional[float] = None
    simulationStart: Optional[float] = None
    simulationEnd: Optional[float] = None
    timeUnit: str
    progress: Optional[float] = None
    updatedAt: Optional[str] = None


class Frame(BaseModel):
    step: Optional[int] = None
    time: Optional[float] = None
    instanceId: Optional[str] = None
    historical: bool


class Entity(BaseModel):
    id: str
    x: float
    y: float

    class Config:
        extra = "allow"


class Node(BaseModel):
    id: str
    label: str
    x: float
    y: float
    voltage: Optional[float] = None


class Edge(BaseModel):
    id: str
    kind: str
    label: str
    from_: str = Field(alias="from")
    to: str
    loading: Optional[float] = None


class Road(BaseModel):
    id: str
    points: List[List[float]]


class Topology(BaseModel):
    nodes: List[Node]
    edges: List[Edge]
    roads: List[Road]


class Availability(BaseModel):
    metrics: bool
    elementValues: bool
    topology: bool
    limitations: List[str]


class Playback(BaseModel):
    index: int
    count: int
    isLatest: bool


class MetricPoint(BaseModel):
    time: Optional[float] = None
    values: Dict[str, Optional[float]]


class Event(BaseModel):
    id: Optional[str] = None
    time: Optional[float] = None
    level: str
    source: str

    class Config:
        extra = "allow"


class MonitorPayload(BaseModel):
    cursor: int
    count: int
    hasMore: bool
    generation: str
    reset: bool
    snapshot: Snapshot
    frame: Frame
    availability: Availability
    playback: Playback
    metrics: Dict[str, Optional[float]]
    metricHistory: List[MetricPoint]
    network: Topology
    entities: List[Entity]
    events: List[Event]
    runEvents: List[Event]
    observables: List[Dict[str, Any]]
