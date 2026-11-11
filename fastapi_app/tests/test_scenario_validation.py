"""DaceDSX scenario validation: schema, step budget and required resources."""
import copy

import pytest

from fastapi_app.frameworks.dacedsx.submission import validate_scenario

BLOCK = {
    "instanceID": "pandapowerWrapper0", "type": "pandapower", "layer": "network", "domain": "energy",
    "stepLength": 3600, "parameters": {}, "resources": {"network.json": "Network"}, "results": {},
    "synchronized": True, "isExternal": False, "responsibilities": [], "observers": [],
}
SCENARIO = {
    "scenarioID": "sce-1", "domainReferences": {}, "simulationStart": 0, "simulationEnd": 86400,
    "execution": {"randomSeed": 1, "syncedParticipants": 1, "constraints": "", "priority": 1},
    "buildingBlocks": [BLOCK], "translators": [], "projectors": [],
}


def scenario(**overrides):
    data = copy.deepcopy(SCENARIO)
    data.update(overrides)
    return data


def test_valid_scenario_lists_required_resources():
    requirements = validate_scenario(scenario())
    assert requirements.scenario_id == "sce-1"
    assert requirements.required_resources == frozenset({"network.json"})


def test_resources_are_collected_across_blocks():
    second = dict(BLOCK, instanceID="SumoWrapper0", domain="traffic", resources={"map.net.xml": "Map"})
    requirements = validate_scenario(scenario(buildingBlocks=[BLOCK, second]))
    assert requirements.required_resources == frozenset({"network.json", "map.net.xml"})


@pytest.mark.parametrize("overrides", [
    {"simulationEnd": 0},
    {"simulationStart": 100, "simulationEnd": 100},
    {"simulationStart": -1},
    {"buildingBlocks": [dict(BLOCK, stepLength=0)]},
    {"buildingBlocks": [dict(BLOCK, domain="finance")]},
    {"execution": {"randomSeed": -1, "syncedParticipants": 1, "constraints": "", "priority": 1}},
])
def test_invalid_scenarios_raise(overrides):
    with pytest.raises(ValueError):
        validate_scenario(scenario(**overrides))


def test_step_budget_is_enforced():
    with pytest.raises(ValueError, match="100,000"):
        validate_scenario(scenario(simulationEnd=100001, buildingBlocks=[dict(BLOCK, stepLength=1)]))
    validate_scenario(scenario(simulationEnd=100000, buildingBlocks=[dict(BLOCK, stepLength=1)]))


def test_missing_fields_raise():
    data = scenario()
    del data["buildingBlocks"]
    with pytest.raises(ValueError):
        validate_scenario(data)
