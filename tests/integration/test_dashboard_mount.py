"""
Tests for Phase 4.3 Unified Frontend Dashboard Mount.
Verifies that:
- GET / redirects to /dashboard
- GET /dashboard (or /dashboard/) serves the HTML control room
- Static files (app.js, styles.css) are served cleanly
"""

from fastapi.testclient import TestClient
from app.main import app


def test_dashboard_root_redirect():
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/")
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/dashboard"


def test_dashboard_html_served():
    client = TestClient(app)
    resp = client.get("/dashboard/")
    assert resp.status_code == 200
    assert "CloudPilot SwitchOps" in resp.text
    assert "Area A: Infrastructure" in resp.text
    assert "Area D: Approval Center" in resp.text
    assert "Area E: Bounded Sandbox Execution" in resp.text


def test_dashboard_static_assets():
    client = TestClient(app)
    resp_js = client.get("/dashboard/app.js")
    assert resp_js.status_code == 200
    assert "CloudPilot SwitchOps" in resp_js.text

    resp_css = client.get("/dashboard/styles.css")
    assert resp_css.status_code == 200
    assert ":root" in resp_css.text
