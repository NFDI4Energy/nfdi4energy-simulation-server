"""MOSAIK_ENABLED gates Mosaik submissions; the editor and worker isolation live elsewhere."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from fastapi_app.core.settings import Settings
from fastapi_app.frameworks.mosaik.routes import router as mosaik_router
from fastapi_app.tasks.submission import SubmissionError


def test_default_is_enabled():
    assert Settings().mosaik_enabled is True


def test_from_env_values(monkeypatch):
    for value, expected in (("true", True), ("TRUE ", True), ("false", False), ("", False), ("1", False), ("yes", False)):
        monkeypatch.setenv("MOSAIK_ENABLED", value)
        assert Settings.from_env().mosaik_enabled is expected
    monkeypatch.delenv("MOSAIK_ENABLED")
    assert Settings.from_env().mosaik_enabled is True


def _mosaik_app(settings):
    """Minimal app with the Mosaik router only; no Redis, RabbitMQ or database."""
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.include_router(mosaik_router)
    app.state.settings = settings

    @app.exception_handler(SubmissionError)
    async def submission_error(request, exc):
        return JSONResponse({"error": str(exc), "code": exc.code}, status_code=exc.status_code)

    return app


def _login(app, client):
    """Bypass require_login and get_db; neither dependency is under test here."""
    from fastapi_app.authentication.auth import require_login
    from fastapi_app.persistence.database_dependencies import get_db
    app.dependency_overrides[require_login] = lambda: type("User", (), {"id": 1})()
    app.dependency_overrides[get_db] = lambda: None
    return client


def test_submit_returns_503_when_disabled():
    app = _mosaik_app(Settings(session_secret="x", auth_disabled=True, mosaik_enabled=False))
    client = _login(app, TestClient(app))
    response = client.post("/api/mosaik/submit", files={"scenario_file": ("scenario.json", b"{}")})
    assert response.status_code == 503
    assert response.json()["code"] == "framework_disabled"


def test_submit_passes_through_when_enabled():
    app = _mosaik_app(Settings(session_secret="x", auth_disabled=True))
    client = _login(app, TestClient(app))

    class FakeSubmission:
        def submit(self, scenario_file, resource_files, user_id, db):
            return {"task_id": "fake", "user_id": user_id}

    app.state.mosaik_submission = FakeSubmission()
    response = client.post("/api/mosaik/submit", files={"scenario_file": ("scenario.json", b"{}")})
    assert response.status_code == 200
    assert response.json() == {"task_id": "fake", "user_id": 1}
