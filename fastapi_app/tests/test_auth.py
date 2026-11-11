"""Authentication routes against an in-memory database; no OIDC provider involved."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from fastapi_app.authentication.auth import LOCAL_USER_ID, create_oauth, router as auth_router
from fastapi_app.core.settings import Settings
from fastapi_app.persistence.database import create_database, init_db


def auth_app(settings, tmp_path):
    """File-backed SQLite: the login route touches the database from a worker thread."""
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.include_router(auth_router)
    engine, factory = create_database(f"sqlite:///{tmp_path}/auth.db")
    init_db(engine)
    app.state.settings, app.state.session_factory = settings, factory
    app.state.oauth = create_oauth(settings)
    return app


def test_me_requires_login(tmp_path):
    client = TestClient(auth_app(Settings(session_secret="x", auth_disabled=True), tmp_path))
    assert client.get("/auth/me").status_code == 401


def test_local_login_when_auth_is_disabled(tmp_path):
    client = TestClient(auth_app(Settings(session_secret="x", auth_disabled=True), tmp_path))
    response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"] == "/dashboard/"
    me = client.get("/auth/me").json()
    assert me["id"] == LOCAL_USER_ID
    assert me["capabilities"] == {"mosaikSubmissionEnabled": True}
    assert client.get("/auth/callback").status_code == 404
    client.get("/auth/logout", follow_redirects=False)
    assert client.get("/auth/me").status_code == 401


def test_local_session_is_invalid_once_oidc_is_enabled(tmp_path):
    app = auth_app(Settings(session_secret="x", auth_disabled=True), tmp_path)
    client = TestClient(app)
    client.get("/auth/login", follow_redirects=False)
    assert client.get("/auth/me").status_code == 200
    app.state.settings = Settings(session_secret="x", oidc_client_id="id", oidc_client_secret="s")
    assert client.get("/auth/me").status_code == 401


def test_oidc_login_redirect_failure_is_reported(tmp_path):
    settings = Settings(session_secret="x", oidc_client_id="id", oidc_client_secret="s",
                        oidc_discovery_url="http://127.0.0.1:9/.well-known/openid-configuration")
    client = TestClient(auth_app(settings, tmp_path))
    response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 502
    assert "authentication provider" in response.json()["error"]
