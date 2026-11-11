"""SubmissionService with an in-memory database and fake Redis/queue."""
import io
from types import SimpleNamespace

import pytest

from fastapi_app.core.settings import Settings
from fastapi_app.infrastructure.rabbitmq_client import PublishUnknown
from fastapi_app.persistence.database import create_database, init_db
from fastapi_app.persistence.models_db import Task, User
from fastapi_app.tasks.contracts import ScenarioRequirements
from fastapi_app.tasks.storage import TaskStorage
from fastapi_app.tasks.submission import SubmissionError, SubmissionService


class FakeRedis:
    def __init__(self):
        self.hashes = {}

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update(mapping)


class FakeQueue:
    def __init__(self, fail=None):
        self.fail, self.published, self.closed = fail, [], False

    def publish(self, task_id, scenario):
        if self.fail:
            raise self.fail
        self.published.append((task_id, scenario))

    def close(self):
        self.closed = True


def upload(name, content):
    return SimpleNamespace(filename=name, file=io.BytesIO(content))


@pytest.fixture
def db():
    engine, factory = create_database("sqlite://")
    init_db(engine)
    with factory() as session:
        session.add(User(id="user-1", sub="sub-1", issuer="test"))
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def service(tmp_path):
    settings = Settings(session_secret="x", auth_disabled=True, scenario_limit=100, resource_limit=100,
                        total_limit=150, resource_count=2)
    storage = TaskStorage(tmp_path / "resources", tmp_path / "results")
    queue = FakeQueue()
    redis = FakeRedis()
    notifications = []

    def validator(scenario):
        return ScenarioRequirements(frozenset(scenario.get("needs", [])), scenario.get("scenarioID"))

    svc = SubmissionService(settings, storage, redis, lambda: queue, validator,
                            lambda task_id, phase, message: notifications.append((task_id, phase, message)))
    svc.queue, svc.redis_fake, svc.notifications = queue, redis, notifications
    return svc


def test_successful_submission(service, db):
    result = service.submit(upload("scenario.json", b'{"scenarioID": "s1", "needs": ["grid.csv"]}'),
                            [upload("grid.csv", b"1,2")], "user-1", db)
    task_id = result["task_id"]
    task = db.get(Task, task_id)
    assert task.status == "PENDING" and task.framework == "dacedsx" and task.scenario_id == "s1"
    assert task.resource_files == ["scenario.json", "grid.csv"]
    assert service.redis_fake.hashes["task:" + task_id]["status"] == "PENDING"
    assert [phase for _, phase, _ in service.notifications] == ["accepted", "validated", "queued"]
    assert service.queue.published[0][0] == task_id and service.queue.closed
    assert (service.storage.inputs(task_id) / "grid.csv").read_text() == "1,2"
    assert service.storage.results(task_id).is_dir()


@pytest.mark.parametrize("body, code", [
    (b"not json", "invalid_scenario"),
    (b"[]", "invalid_scenario"),
    (b"{}", "invalid_scenario"),
    (b'{"scenarioID": "s1", "needs": ["grid.csv"]}', "missing_resources"),
])
def test_invalid_or_incomplete_scenario_is_rejected_before_persisting(service, db, body, code):
    with pytest.raises(SubmissionError) as ctx:
        service.submit(upload("scenario.json", body), [], "user-1", db)
    assert ctx.value.code == code
    assert db.query(Task).count() == 0
    assert service.notifications == []
    assert [p for p in service.storage.resources_root.iterdir()] == []  # staging dir cleaned up


def test_upload_limits(service, db):
    with pytest.raises(SubmissionError) as ctx:
        service.submit(upload("scenario.json", b"{" + b" " * 200 + b"}"), [], "user-1", db)
    assert ctx.value.code == "upload_limit_exceeded" and ctx.value.status_code == 413
    with pytest.raises(SubmissionError) as ctx:
        service.submit(upload("scenario.json", b'{"a": 1}'), [upload(f"r{i}", b"x") for i in range(3)], "user-1", db)
    assert ctx.value.code == "upload_limit_exceeded"


def test_bad_filenames_are_rejected(service, db):
    with pytest.raises(SubmissionError) as ctx:
        service.submit(upload("../scenario.json", b'{"a": 1}'), [], "user-1", db)
    assert ctx.value.code == "invalid_filename"
    with pytest.raises(SubmissionError) as ctx:
        service.submit(upload("a.json", b'{"a": 1}'), [upload("a.json", b"x")], "user-1", db)
    assert ctx.value.code == "invalid_filename"


def test_unknown_delivery_keeps_task_pending(service, db):
    service.queue.fail = PublishUnknown("delivery could not be confirmed")
    with pytest.raises(SubmissionError) as ctx:
        service.submit(upload("scenario.json", b'{"a": 1}'), [], "user-1", db)
    assert ctx.value.code == "submission_outcome_unknown" and ctx.value.status_code == 503
    task = db.get(Task, ctx.value.task_id)
    assert task.status == "PENDING"
    assert service.notifications[-1][1] == "unknown"


def test_broker_failure_marks_task_error(service, db):
    service.queue.fail = ConnectionError("broker down")
    with pytest.raises(SubmissionError) as ctx:
        service.submit(upload("scenario.json", b'{"a": 1}'), [], "user-1", db)
    assert ctx.value.code == "submission_failed"
    task = db.get(Task, ctx.value.task_id)
    assert task.status == "ERROR"
    assert service.redis_fake.hashes["task:" + task.id]["status"] == "ERROR"
    assert service.notifications[-1][1] == "failed"


def test_unsupported_framework():
    with pytest.raises(ValueError):
        SubmissionService(Settings(), None, None, None, framework="other")
