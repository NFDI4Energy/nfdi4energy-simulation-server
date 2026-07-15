import json
import os
import signal
import sys
import time

import redis
from confluent_kafka import Consumer, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic

from log_persistence import append_dead_letter, persist_structured_event, status_from_event


EVENT_TOPIC = os.environ.get("LOG_EVENT_TOPIC", "simservice.logs.events")
KAFKA_BOOTSTRAP_SERVERS = os.environ.get(
    "KAFKA_BOOTSTRAP_SERVERS",
    os.environ.get("KAFKA_BROKER", "broker.kafka.svc.cluster.local:9092"),
)
CONSUMER_GROUP = os.environ.get("LOG_CONSUMER_GROUP", "simaas-log-consumer")
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
TOPIC_PARTITIONS = int(os.environ.get("LOG_EVENT_TOPIC_PARTITIONS", "1"))
TOPIC_REPLICATION_FACTOR = int(os.environ.get("LOG_EVENT_TOPIC_REPLICATION_FACTOR", "1"))

running = True


def stop(_signum, _frame):
    global running
    running = False


def decode_event(raw_value):
    if raw_value is None:
        raise ValueError("empty Kafka message")

    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8")

    return json.loads(raw_value)


def update_redis_status(redis_client, event):
    if not isinstance(event, dict) or not event.get("task_id"):
        return

    status, error = status_from_event(event)
    if not status:
        return

    mapping = {"status": status}
    if error is not None:
        mapping["error"] = error
    redis_client.hset(f"task:{event['task_id']}", mapping=mapping)


def ensure_topic_exists():
    admin = AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS})
    metadata = admin.list_topics(timeout=10)
    if EVENT_TOPIC in metadata.topics and metadata.topics[EVENT_TOPIC].error is None:
        return

    futures = admin.create_topics(
        [NewTopic(EVENT_TOPIC, TOPIC_PARTITIONS, TOPIC_REPLICATION_FACTOR)]
    )
    try:
        futures[EVENT_TOPIC].result(timeout=15)
        print(f"[log-consumer] created topic {EVENT_TOPIC}", flush=True)
    except Exception as exc:
        if "TopicAlreadyExists" in str(exc) or "already exists" in str(exc):
            return
        raise


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    redis_client = redis.Redis(host=REDIS_HOST, port=6379, db=0)
    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
            "group.id": CONSUMER_GROUP,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
    )

    while running:
        try:
            ensure_topic_exists()
            consumer.subscribe([EVENT_TOPIC])
            print(f"[log-consumer] subscribed to {EVENT_TOPIC} at {KAFKA_BOOTSTRAP_SERVERS}", flush=True)
            break
        except KafkaException as exc:
            print(f"[log-consumer] subscribe failed: {exc}; retrying", flush=True)
            time.sleep(5)

    try:
        while running:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print(f"[log-consumer] Kafka error: {msg.error()}", flush=True)
                continue

            try:
                event = decode_event(msg.value())
                if persist_structured_event(event):
                    print(
                        f"[log-consumer] persisted {event.get('event_code')} for {event.get('task_id')}",
                        flush=True,
                    )
                update_redis_status(redis_client, event)
            except Exception as exc:
                append_dead_letter(str(exc), msg.value().decode("utf-8", errors="replace") if msg.value() else None)
                print(f"[log-consumer] failed to process event: {exc}", flush=True)
    finally:
        consumer.close()
        print("[log-consumer] stopped", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[log-consumer] fatal error: {exc}", flush=True)
        sys.exit(1)
