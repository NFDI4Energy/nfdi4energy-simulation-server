import json
import fcntl
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class SimulationEventEmitter:
    EVENT_TOPIC = "simservice.logs.events"
    _file_lock = threading.RLock()

    def __init__(self, task_id, source, component, producer=None, results_dir=None):
        self.task_id = task_id
        self.source = source
        self.component = component
        self.producer = producer
        self.results_dir = Path(results_dir) if results_dir else None

    def emit(self, category, event_code, message, progress=None, simulation_time=None, metadata=None):
        if not self.task_id:
            return

        event = {
            "id": f"evt_{uuid.uuid4()}",
            "schema_version": "1.0",
            "task_id": self.task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": self.source,
            "category": category,
            "component": self.component,
            "event_code": event_code,
            "message": message,
        }
        if progress is not None:
            event["progress"] = progress
        if simulation_time is not None:
            event["simulation_time"] = simulation_time
        if metadata is not None:
            event["metadata"] = metadata

        self._persist_event(event, category == "METRIC")
        self._publish(event)

    def _persist_event(self, event, metric):
        if not self.results_dir:
            return
        try:
            directory = self.results_dir / "events"
            directory.mkdir(parents=True, exist_ok=True)
            with self._file_lock, (directory / ".writer.lock").open("a+b") as lock:
                os.chmod(directory / ".writer.lock", 0o666)
                fcntl.lockf(lock, fcntl.LOCK_EX)
                try:
                    self._append_jsonl("structured_events.jsonl", event)
                    if metric:
                        self._append_jsonl("metrics.jsonl", event)
                finally:
                    fcntl.lockf(lock, fcntl.LOCK_UN)
        except OSError:
            logging.getLogger(__name__).warning("Local event persistence failed; attempting Kafka", exc_info=True)

    def metric_snapshot(self, simulation_time, metrics, progress=None, metadata=None):
        meta = {"metrics": metrics}
        if metadata:
            meta.update(metadata)
        self.emit(
            "METRIC",
            "METRIC_SNAPSHOT",
            "PandaPower metric snapshot",
            progress=progress,
            simulation_time=simulation_time,
            metadata=meta,
        )

    def _append_jsonl(self, name, event):
        if not self.results_dir:
            return
        event_dir = self.results_dir / "events"
        event_dir.mkdir(parents=True, exist_ok=True)
        with (event_dir / name).open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _publish(self, event):
        if not self.producer:
            return
        try:
            self.producer.produce(self.EVENT_TOPIC, json.dumps(event), key=self.task_id)
        except Exception:
            pass
