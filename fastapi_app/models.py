from pydantic import BaseModel
from typing import List

class Execution(BaseModel):
    randomSeed: int
    syncedParticipants: int
    constraints: str
    priority: int

class BuildingBlock(BaseModel):
    instanceID: str
    type: str
    layer: str
    domain: str
    stepLength: int
    parameters: dict
    resources: dict
    results: dict
    synchronized: bool
    isExternal: bool
    responsibilities: list
    observers: list

class Scenario(BaseModel):
    scenarioID: str
    domainReferences: dict
    simulationStart: int
    simulationEnd: int
    execution: Execution
    buildingBlocks: List[BuildingBlock]
    translators: list
    projectors: list
