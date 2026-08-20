import pika
import json
import os
from abc import ABC, abstractmethod
from typing import List, Tuple

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")


"""
Adding a New Framework
----------------------
1. Declare the queue in SimulationQueue.__init__:
       self.channel.queue_declare(queue="myframework_requests", durable=True)

2. Create a handler class subclassing SimulationHandler:
       framework_name property → return the framework identifier
       Override parse_scenario, get_resources_dir, publish if needed (defaults exist)

3. Register it in the HANDLERS dict:
       HANDLERS = { ..., "myframework": MyFrameworkSimulationHandler() }

The /submit endpoint dispatches entirely through get_handler(framework).
"""


class SimulationQueue:
    def __init__(self):
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST)
        )
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue="dacedsx_requests", durable=True)
        self.channel.queue_declare(queue="mosaik_requests", durable=True)

    def close(self):
        self.connection.close()


class SimulationHandler(ABC):
    @property
    @abstractmethod
    def framework_name(self) -> str:
        """The framework identifier used as the queue name prefix and Redis field value."""
        pass

    def publish(self, task_id: str, scenario: dict, queue: SimulationQueue):
        message = {"task_id": task_id, "scenario": scenario}
        queue.channel.basic_publish(
            exchange="",
            routing_key=f"{self.framework_name}_requests",
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2),
        )

    def parse_scenario(self, files: List[Tuple[str, bytes]]) -> dict:
        if not files:
            raise ValueError("No files provided")
        return json.loads(files[0][1])

    def get_resources_dir(self, task_id: str) -> str:
        return os.path.join(os.environ.get("RESOURCES_DIR", "/data/resources"), task_id)

    def get_redis_fields(self) -> dict:
        return {"framework": self.framework_name}


class DaceDSXSimulationHandler(SimulationHandler):
    @property
    def framework_name(self) -> str:
        return "dacedsx"


class MosaikSimulationHandler(SimulationHandler):
    @property
    def framework_name(self) -> str:
        return "mosaik"


HANDLERS = {
    "dacedsx": DaceDSXSimulationHandler(),
    "mosaik": MosaikSimulationHandler(),
}


def get_handler(framework: str) -> SimulationHandler:
    if framework not in HANDLERS:
        raise ValueError(f"Unknown framework: {framework}")
    return HANDLERS[framework]