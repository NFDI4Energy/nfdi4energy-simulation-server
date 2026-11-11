"""The dashboard bundle is built in the image; a checkout without it must still start."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_app.webapp import mount_dashboard


def test_missing_bundle_is_skipped_with_warning(tmp_path, caplog):
    app = FastAPI()
    assert mount_dashboard(app, tmp_path / "svelte-dist") is False
    assert "npm run build" in caplog.text
    assert TestClient(app).get("/dashboard/").status_code == 404


def test_present_bundle_is_served(tmp_path):
    dist = tmp_path / "svelte-dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>dashboard</h1>")
    app = FastAPI()
    assert mount_dashboard(app, dist) is True
    response = TestClient(app).get("/dashboard/")
    assert response.status_code == 200
    assert "dashboard" in response.text
