from pydantic import BaseModel, Field, root_validator
from typing import List, Literal

class Execution(BaseModel):
    randomSeed: int = Field(..., ge=0, description="Random seed must be non-negative")
    syncedParticipants: int
    constraints: str
    priority: int

class BuildingBlock(BaseModel):
    instanceID: str
    type: str
    layer: str
    domain: Literal["energy", "communication", "traffic"]
    stepLength: int = Field(..., gt=0, description="Step length must be strictly positive")
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
    simulationStart: int = Field(..., ge=0, description="Simulation start time must be non-negative")
    simulationEnd: int = Field(..., gt=0, description="Simulation end time must be greater than 0")
    execution: Execution
    buildingBlocks: List[BuildingBlock]
    translators: list
    projectors: list

    @root_validator()
    def validate_simulation_steps(cls, values):
        start = values.get('simulationStart')
        end = values.get('simulationEnd')
        blocks = values.get('buildingBlocks')

        if start is not None and end is not None:
            if end <= start:
                raise ValueError("simulationEnd must be strictly greater than simulationStart")
            
            if blocks:
                duration = end - start
                for bb in blocks:
                    if bb.stepLength and bb.stepLength > 0:
                        steps = duration / bb.stepLength
                        if steps > 100000:
                            raise ValueError(
                                f"Total steps ({int(steps)}) for building block '{bb.instanceID}' "
                                f"exceeds the maximum limit of 100,000. Please increase stepLength or reduce simulation duration."
                            )
        return values
