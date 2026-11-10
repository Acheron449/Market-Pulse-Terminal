"""GET /api/market contract tests (SRS §5.3, AGENTS.md §8).

Every response is validated against the JSON Schema itself, not just the Pydantic model,
so a drift between the generator and the schema cannot hide here.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads(
    (REPO_ROOT / "shared" / "schema" / "market-snapshot.schema.json").read_text(encoding="utf-8")
)


def client(**kwargs: Any) -> TestClient:
    return TestClient(create_app(**kwargs))


def test_market_returns_a_schema_valid_snapshot() -> None:
    jsonschema = pytest.importorskip("jsonschema", reason="dev dependency jsonschema absent")

    response = client().get("/api/market")

    assert response.status_code == 200
    body = response.json()
    jsonschema.validate(instance=body, schema=SCHEMA)
    assert body["schemaVersion"] == 1
    assert set(body) == set(SCHEMA["required"])
    assert "feed_delay_seconds" not in body


def test_market_response_is_flagged_as_replay() -> None:
    body = client().get("/api/market").json()

    assert set(body["status"].values()) == {"stale"}
    disclosures = [
        error
        for error in body["errors"]
        if error["section"] == "snapshot" and error["provider"] == "replay"
    ]
    assert len(disclosures) == 1
    assert len(body["indexes"]) == 5
    assert body["indexes"][4]["symbol"] == "^VIX"
    assert body["indexes"][4]["invert"] is True


def test_market_accepts_the_refresh_parameter() -> None:
    # FR-16 lands with the scheduler; until then the parameter must not 422.
    response = client().get("/api/market?refresh=1")

    assert response.status_code == 200


def test_market_answers_503_before_the_first_build() -> None:
    response = client(seed_replay=False).get("/api/market")

    assert response.status_code == 503
    assert "snapshot" in response.json()["detail"]
