import os
import signal
import sys
import time

from confluent_kafka import Consumer, KafkaException, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

from fastapi_app.frameworks.dacedsx.events.persistence import close_persistence
from fastapi_app.frameworks.dacedsx.events.ingestion import persist_and_commit


EVENT_TOPIC = os.environ.get("LOG_EVENT_TOPIC", "simservice.logs.events")
KAFKA_BOOTSTRAP_SERVERS = os.environ.get(
    "KAFKA_BOOTSTRAP_SERVERS",
    os.environ.get("KAFKA_BROKER", "broker.kafka.svc.cluster.local:9092"),
)
CONSUMER_GROUP = os.environ.get("LOG_CONSUMER_GROUP", "simaas-log-consumer")
TOPIC_PARTITIONS = int(os.environ.get("LOG_EVENT_TOPIC_PARTITIONS", "1"))
TOPIC_REPLICATION_FACTOR = int(os.environ.get("LOG_EVENT_TOPIC_REPLICATION_FACTOR", "1"))

running = True


def stop(_signum, _frame):
    global running
    running = False


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

    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
            "group.id": CONSUMER_GROUP,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
        }
    )

    try:
        while running:
            try:
                ensure_topic_exists()
                consumer.subscribe([EVENT_TOPIC])
                print(f"[log-consumer] subscribed to {EVENT_TOPIC} at {KAFKA_BOOTSTRAP_SERVERS}", flush=True)
                break
            except KafkaException as exc:
                print(f"[log-consumer] subscribe failed: {exc}; retrying", flush=True)
                time.sleep(5)

        while running:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print(f"[log-consumer] Kafka error: {msg.error()}", flush=True)
                continue

            try:
                if persist_and_commit(consumer, msg):
                    print(
                        "[log-consumer] persisted event",
                        flush=True,
                    )
            except Exception as exc:
                print(f"[log-consumer] persistence/commit failed; retrying: {exc}", flush=True)
                consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
                time.sleep(1)
    finally:
        consumer.close()
        close_persistence()
        print("[log-consumer] stopped", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[log-consumer] fatal error: {exc}", flush=True)
        sys.exit(1)
