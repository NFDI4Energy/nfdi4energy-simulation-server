import json
import logging
import shutil
import uuid
from typing import Optional

from fastapi_app.persistence.models_db import Task
from fastapi_app.tasks.storage import StorageError, flat_filename
from fastapi_app.infrastructure.rabbitmq_client import PublishUnknown
from fastapi_app.tasks.contracts import ScenarioValidator, LifecycleNotifier

logger = logging.getLogger(__name__)


class SubmissionError(Exception):
    def __init__(self, message, code, status_code=400, task_id=None):
        super().__init__(message)
        self.code, self.status_code, self.task_id = code, status_code, task_id


class SubmissionService:
    def __init__(self, settings, storage, redis_client, queue_factory,
                 validator: ScenarioValidator, notifier: Optional[LifecycleNotifier] = None):
        self.settings, self.storage, self.redis = settings, storage, redis_client
        self.queue_factory = queue_factory
        self.validator, self.notifier = validator, notifier

    def _notify(self, task_id, phase, message=None):
        if self.notifier is None:
            return
        try:
            self.notifier(task_id, phase, message)
        except Exception:
            logger.exception("Supplementary event persistence failed for task %s", task_id)

    def _copy(self, upload, destination, limit, total):
        written = 0
        upload.file.seek(0)
        with open(destination, "xb") as output:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                total += len(chunk)
                if written > limit or total > self.settings.total_limit:
                    raise SubmissionError("Upload limit exceeded", "upload_limit_exceeded", 413)
                output.write(chunk)
        return total

    def _failure(self, db, task, message):
        try:
            task.status, task.error_message = "ERROR", message
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not record submission failure for %s", task.id)
        try:
            self.redis.hset("task:" + task.id, mapping={"status": "ERROR", "error": message})
        except Exception:
            logger.exception("Could not record Redis submission failure for %s", task.id)
        self._notify(task.id, "failed", message)

    def submit(self, scenario_file, resource_files, owner_id, db):
        stage = None
        task_id = str(uuid.uuid4())
        task = None
        persisted = False
        queue = None
        phase = "storage"
        try:
            if len(resource_files) > self.settings.resource_count:
                raise SubmissionError("Too many resource files", "upload_limit_exceeded", 413)
            filenames = [flat_filename(f.filename) for f in [scenario_file] + resource_files]
            if len(set(filenames)) != len(filenames):
                raise StorageError("Duplicate or colliding upload filenames")
            stage = self.storage.stage()
            total = self._copy(scenario_file, stage / filenames[0], self.settings.scenario_limit, 0)
            try:
                with open(stage / filenames[0], encoding="utf-8") as source:
                    scenario_dict = json.load(source)
                if not isinstance(scenario_dict, dict):
                    raise ValueError("Scenario must be a JSON object")
                json.dumps(scenario_dict, allow_nan=False)
                requirements = self.validator(scenario_dict)
            except (ValueError, UnicodeDecodeError) as exc:
                raise SubmissionError("Invalid scenario: " + str(exc), "invalid_scenario") from exc
            required = {flat_filename(name) for name in requirements.required_resources}
            missing = required - set(filenames[1:])
            if missing:
                raise SubmissionError("Missing required resource files: " + ", ".join(sorted(missing)), "missing_resources")
            for upload, name in zip(resource_files, filenames[1:]):
                total = self._copy(upload, stage / name, self.settings.resource_limit, total)
            self.storage.finalize(stage, task_id)
            stage = None
            phase = "metadata"
            task = Task(id=task_id, user_id=owner_id, scenario_id=requirements.scenario_id,
                        resource_files=filenames, status="PENDING")
            db.add(task)
            db.commit()
            persisted = True
            phase = "tracker"
            self.redis.hset("task:" + task_id, mapping={"status": "PENDING", "files": "[]", "error": ""})
            self._notify(task_id, "accepted")
            self._notify(task_id, "validated")
            phase = "broker"
            queue = self.queue_factory()
            try:
                queue.publish(task_id, scenario_dict)
            except PublishUnknown as exc:
                # Never overwrite worker state or retry a potentially delivered request.
                self._notify(task_id, "unknown", str(exc))
                raise SubmissionError(str(exc), "submission_outcome_unknown", 503, task_id) from exc
            self._notify(task_id, "queued")
            return {"task_id": task_id}
        except SubmissionError as exc:
            if persisted and exc.code != "submission_outcome_unknown":
                self._failure(db, task, str(exc))
            raise
        except StorageError as exc:
            raise SubmissionError(str(exc), "invalid_filename") from exc
        except Exception as exc:
            db.rollback()
            if persisted:
                self._failure(db, task, "Simulation request could not be submitted")
            logger.exception("Submission failed for task %s", task_id)
            if phase == "storage" and isinstance(exc, OSError):
                raise SubmissionError("Task storage is unavailable", "storage_unavailable", 503) from exc
            raise SubmissionError("Simulation request could not be submitted", "submission_failed", 503,
                                  task_id if persisted else None) from exc
        finally:
            if queue is not None:
                try:
                    queue.close()
                except Exception:
                    logger.exception("Could not close submission broker connection")
            if stage is not None:
                shutil.rmtree(str(stage), ignore_errors=True)
            if not persisted:
                try:
                    self.storage.discard(task_id)
                except OSError:
                    logger.exception("Could not clean incomplete task %s", task_id)
