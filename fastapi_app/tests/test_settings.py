"""Environment parsing and start-up validation of Settings."""
import pytest

from fastapi_app.core.settings import Settings


def test_defaults_are_safe():
    settings = Settings()
    assert settings.auth_disabled is False
    assert settings.mosaik_enabled is True
    assert settings.session_secret == ""


def test_from_env_reads_values(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", " TRUE ")
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    monkeypatch.setenv("SCENARIO_UPLOAD_LIMIT", "1234")
    monkeypatch.setenv("REDIS_HOST", "cache")
    settings = Settings.from_env()
    assert settings.auth_disabled is True
    assert settings.session_secret == "s3cret"
    assert settings.scenario_limit == 1234
    assert settings.redis_host == "cache"


def test_secret_is_not_in_repr():
    assert "s3cret" not in repr(Settings(session_secret="s3cret", oidc_client_secret="s3cret"))


def test_validate_requires_session_secret():
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        Settings().validate()


def test_validate_requires_oidc_credentials_when_auth_is_on():
    with pytest.raises(RuntimeError, match="OIDC_CLIENT_ID"):
        Settings(session_secret="x").validate()
    Settings(session_secret="x", oidc_client_id="id", oidc_client_secret="secret").validate()


def test_validate_rejects_nonpositive_limits():
    with pytest.raises(RuntimeError, match="Upload limits"):
        Settings(session_secret="x", auth_disabled=True, resource_count=0).validate()
