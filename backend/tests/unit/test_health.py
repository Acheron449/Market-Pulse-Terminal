"""Health endpoint smoke test (SRS §5.3)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok_and_contract_version() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["schemaVersion"] == 1
    assert body["service"] == "Market Pulse Terminal"
    assert body["version"]


def test_health_ignores_a_stray_query_string() -> None:
    # The route takes no parameters; an extra query string must not change the answer.
    response = client.get("/api/health?probe=1")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
