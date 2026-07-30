import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


FASTAPI_DIR = os.path.dirname(os.path.dirname(__file__))
if FASTAPI_DIR not in sys.path:
    sys.path.insert(0, FASTAPI_DIR)

import webapp


class TrafficMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.resources_dir = os.path.join(self.temporary_directory.name, "resources")
        self.results_dir = os.path.join(self.temporary_directory.name, "results")
        self.task_id = "traffic-task"
        os.makedirs(os.path.join(self.resources_dir, self.task_id))
        os.makedirs(os.path.join(self.results_dir, self.task_id, "events"))

        network = """<net>
            <edge id="west-east"><lane id="west-east_0" shape="0,0 50,0 100,0"/></edge>
            <edge id=":internal" function="internal"><lane id=":internal_0" shape="50,0 50,5"/></edge>
        </net>"""
        with open(os.path.join(self.resources_dir, self.task_id, "test.net.xml"), "w", encoding="utf-8") as output:
            output.write(network)
        with open(os.path.join(self.resources_dir, self.task_id, "scenario.json"), "w", encoding="utf-8") as output:
            json.dump({"buildingBlocks": [{"type": "SumoWrapper", "domain": "traffic"}]}, output)

        self.metric_events = [
            self.metric_event("metric-1", 1000, 1, "vehicle-1", 25, 0),
            self.metric_event("metric-2", 2000, 2, "vehicle-2", 75, 0),
        ]
        metrics_path = os.path.join(self.results_dir, self.task_id, "events", "metrics.jsonl")
        structured_path = os.path.join(self.results_dir, self.task_id, "events", "structured_events.jsonl")
        for path in (metrics_path, structured_path):
            with open(path, "w", encoding="utf-8") as output:
                for event in self.metric_events:
                    output.write(json.dumps(event) + "\n")

    def tearDown(self):
        self.temporary_directory.cleanup()

    @staticmethod
    def metric_event(event_id, simulation_time, step, vehicle_id, x, y):
        return {
            "id": event_id,
            "timestamp": "2026-01-01T00:00:00Z",
            "category": "METRIC",
            "component": "SumoWrapper",
            "simulation_time": simulation_time,
            "metadata": {
                "domain": "traffic",
                "step": step,
                "total_steps": 2,
                "metrics": {
                    "vehicles.active": 1,
                    "vehicles.arrived": step - 1,
                    "speed.avg_mps": 10.0,
                },
                "entities": [
                    {
                        "id": vehicle_id,
                        "kind": "vehicle",
                        "x": x,
                        "y": y,
                        "speed": 10.0,
                        "edge": "west-east",
                        "status": "moving",
                    }
                ],
            },
        }

    def test_history_index_selects_matching_traffic_entities(self):
        with patch.object(webapp, "RESOURCES_DIR", self.resources_dir), patch.object(
            webapp, "RESULTS_DIR", self.results_dir
        ), patch.object(webapp, "task_runtime_status", return_value={"status": "DONE", "error": ""}):
            first = webapp.build_monitor_payload(self.task_id, history_index=0)
            second = webapp.build_monitor_payload(self.task_id, history_index=1)

        self.assertEqual(first["snapshot"]["domain"], "traffic")
        self.assertEqual(first["entities"][0]["id"], "vehicle-1")
        self.assertEqual(second["entities"][0]["id"], "vehicle-2")
        self.assertEqual(second["snapshot"]["progress"], 1.0)
        self.assertEqual(first["snapshot"]["simulationTime"], 1.0)
        self.assertEqual(second["snapshot"]["simulationEnd"], 2.0)
        self.assertEqual([point["time"] for point in second["metricHistory"]], [1.0, 2.0])
        self.assertEqual(second["playback"], {"index": 1, "count": 2, "isLatest": True})
        self.assertEqual([road["id"] for road in second["network"]["roads"]], ["west-east"])
        self.assertEqual(second["network"]["roads"][0]["points"], [[5.0, 50.0], [50.0, 50.0], [95.0, 50.0]])

    def test_scenario_domain_is_used_before_the_first_metric(self):
        with patch.object(webapp, "RESOURCES_DIR", self.resources_dir):
            domain = webapp.monitor_domain(self.task_id, [], [])

        self.assertEqual(domain, "traffic")

    def test_later_wrapper_completion_recovers_stale_redis_status(self):
        lifecycle_events = [
            {"event_code": "TASK_FAILED", "message": "First attempt failed"},
            {"event_code": "TASK_STARTED", "message": "Retry started"},
            {"event_code": "WRAPPER_COMPLETED", "message": "Retry completed"},
        ]
        structured_path = os.path.join(
            self.results_dir, self.task_id, "events", "structured_events.jsonl"
        )
        with open(structured_path, "a", encoding="utf-8") as output:
            for event in lifecycle_events:
                output.write(json.dumps(event) + "\n")

        with patch.object(webapp, "RESOURCES_DIR", self.resources_dir), patch.object(
            webapp, "RESULTS_DIR", self.results_dir
        ), patch.object(
            webapp,
            "task_runtime_status",
            return_value={"status": "RUNNING", "error": "Stale worker state"},
        ):
            payload = webapp.build_monitor_payload(self.task_id)

        self.assertEqual(payload["snapshot"]["status"], "DONE")
        self.assertEqual(payload["snapshot"]["error"], "")
        self.assertEqual(payload["snapshot"]["domain"], "traffic")

    def test_legacy_result_artifact_recovers_missing_redis_status(self):
        result_path = os.path.join(self.results_dir, self.task_id, "bus_vm_pu.csv")
        with open(result_path, "w", encoding="utf-8") as output:
            output.write("0,1.0\n")

        with patch.object(webapp, "RESULTS_DIR", self.results_dir), patch.object(
            webapp,
            "task_runtime_status",
            return_value={"status": "PENDING", "error": "", "redis_found": False},
        ), patch.object(webapp.redis_client, "hset") as redis_hset:
            runtime = webapp.resolved_task_status(self.task_id)

        self.assertEqual(runtime["status"], "DONE")
        redis_hset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
