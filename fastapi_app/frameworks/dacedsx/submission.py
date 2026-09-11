"""DaceDSX scenario requirements and task lifecycle event mapping."""
import uuid
from datetime import datetime, timezone

from fastapi_app.frameworks.dacedsx.scenario import Scenario
from fastapi_app.frameworks.dacedsx.events.persistence import persist_structured_event
from fastapi_app.tasks.contracts import ScenarioRequirements


def validate_scenario(scenario_dict):
    scenario = Scenario(**scenario_dict)
    required = frozenset(name for block in scenario.buildingBlocks
                         for name in block.resources)
    return ScenarioRequirements(required, scenario_dict.get("scenarioID"))


class LifecycleEvents:
    EVENTS = {
        "accepted": ("TASK_ACCEPTED", "Simulation task accepted", "PROGRESS"),
        "validated": ("SCENARIO_VALIDATED", "Scenario and resources validated", "VALIDATION"),
        "queued": ("TASK_QUEUED", "Simulation task queued", "PROGRESS"),
        "failed": ("TASK_FAILED", "Simulation request could not be submitted", "ERROR"),
        "unknown": ("SUBMISSION_OUTCOME_UNKNOWN", "Simulation request delivery could not be confirmed", "WARNING"),
    }

    def __init__(self, storage):
        self.storage = storage

    def __call__(self, task_id, phase, message=None):
        code, default_message, category = self.EVENTS[phase]
        persist_structured_event({
            "id": "evt_" + str(uuid.uuid4()), "schema_version": "1.0",
            "task_id": task_id, "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "web", "component": "WebService", "category": category,
            "event_code": code, "message": message if message is not None else default_message,
        }, self.storage)
