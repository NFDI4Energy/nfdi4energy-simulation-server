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
        Settings(session_secret="x", auth_disabled=True, environment="development", resource_count=0).validate()


def test_environment_defaults_to_production(monkeypatch):
    monkeypatch.delenv("SIMAAS_ENV", raising=False)
    assert Settings.from_env().environment == "production"
    monkeypatch.setenv("SIMAAS_ENV", " Development ")
    assert Settings.from_env().environment == "development"


def test_auth_bypass_is_refused_outside_development():
    with pytest.raises(RuntimeError, match="SIMAAS_ENV=development"):
        Settings(session_secret="x", auth_disabled=True).validate()
    with pytest.raises(RuntimeError, match="SIMAAS_ENV"):
        Settings(session_secret="x", auth_disabled=True, environment="staging").validate()
    Settings(session_secret="x", auth_disabled=True, environment="development").validate()


def test_unknown_environment_is_rejected():
    with pytest.raises(RuntimeError, match="SIMAAS_ENV"):
        Settings(session_secret="x", oidc_client_id="id", oidc_client_secret="s", environment="prod").validate()
