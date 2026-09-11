"""Confirmed publication; ambiguous delivery is surfaced, never retried here."""
import json
import logging

logger = logging.getLogger(__name__)


class PublishRejected(Exception):
    pass


class PublishUnknown(Exception):
    pass


class SimulationQueue:
    def __init__(self, host, queue_name):
        import pika
        self.queue_name = queue_name
        self.connection = None
        try:
            self.connection = pika.BlockingConnection(pika.ConnectionParameters(
                host=host,
                connection_attempts=1, socket_timeout=5, stack_timeout=10,
                blocked_connection_timeout=10, heartbeat=30))
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue=self.queue_name, durable=True)
            self.channel.confirm_delivery()
        except Exception:
            self.close()
            raise

    def publish(self, task_id, scenario):
        import pika
        try:
            self.channel.basic_publish(
                exchange="", routing_key=self.queue_name,
                body=json.dumps({"task_id": task_id, "scenario": scenario}),
                properties=pika.BasicProperties(delivery_mode=2), mandatory=True)
        except (pika.exceptions.UnroutableError, pika.exceptions.NackError) as exc:
            raise PublishRejected("Simulation request was rejected by the broker") from exc
        except Exception as exc:
            raise PublishUnknown("Simulation request delivery could not be confirmed") from exc

    def close(self):
        if self.connection is not None:
            try:
                if self.connection.is_open:
                    self.connection.close()
            except Exception:
                logger.warning("Failed to close RabbitMQ connection", exc_info=True)
