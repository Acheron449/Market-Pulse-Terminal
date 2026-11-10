"""API surface: refresh cooldown, SSE contract and chart endpoints (FR-14, FR-16, FR-28)."""

import json
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

import app.api.market as market_module
from app.core.config import get_settings
from app.main import create_app
from app.providers.base import Bar
from app.providers.registry import FetchResult
from app.services.chart_service import ChartService
from app.services.snapshot_store import SnapshotStore


class FakeService:
    def __init__(self, store: SnapshotStore) -> None:
        self.refreshes = 0
        self._store = store

    async def refresh(self, *, force: bool = False) -> Any:
        self.refreshes += 1
        return self._store.current()


class FakeHistoryRegistry:
    async def fetch(self, capability: str, method: str, *args: Any) -> FetchResult:
        symbol, resolution, start_ms, end_ms = args
        bars = [
            Bar(time=start_ms + index * 300_000, open=100.0, high=101.0, low=99.0, close=100.5)
            for index in range(12)
            if start_ms + index * 300_000 < end_ms
        ]
        return FetchResult(provider="fake", value=bars)


@pytest.fixture(autouse=True)
def clear_cooldowns() -> Iterator[None]:
    market_module._last_refresh.clear()
    yield
    market_module._last_refresh.clear()


def client() -> TestClient:
    return TestClient(create_app())


def test_refresh_parameter_is_rate_limited() -> None:
    application = create_app()
    service = FakeService(application.state.snapshot_store)
    application.state.snapshot_service = service
    test_client = TestClient(application)

    first = test_client.get("/api/market?refresh=1")
    second = test_client.get("/api/market?refresh=1")

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1
    assert service.refreshes == 1


def test_stream_sends_a_snapshot_event() -> None:
    test_client = client()
    with test_client.stream("GET", "/api/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data: "):
                body = json.loads(line.removeprefix("data: "))
                assert body["schemaVersion"] == 1
                assert len(body["indexes"]) == 5
                break
        else:  # pragma: no cover - the stream must always start with a snapshot
            raise AssertionError("no snapshot event")


def test_ui_config_exposes_no_secrets() -> None:
    body = client().get("/api/config").json()

    assert body["schemaVersion"] == 1
    assert body["refreshCooldownSeconds"] == get_settings().refresh_cooldown_seconds
    assert "apiKey" not in json.dumps(body)


def test_health_reports_providers_and_sections() -> None:
    body = client().get("/api/health").json()

    assert body["status"] in {"ok", "degraded"}
    assert body["mode"] == "replay"
    assert body["sections"]
    names = {provider["name"] for provider in body["providers"]}
    assert {"yfinance", "alpaca", "finnhub", "calendar"} <= names


def test_chart_config_and_symbol_info() -> None:
    test_client = client()

    config = test_client.get("/api/chart/config").json()
    assert config["supportedResolutions"] == ["1", "5", "15", "60", "1D"]
    assert config["supportsSearch"] is True

    info = test_client.get("/api/chart/symbols/%5EGSPC").json()
    assert info["symbol"] == "^GSPC"
    assert info["visiblePlotsSet"] == "ohlc"
    assert info["session"] == "0930-1600"
    assert "sessionHolidays" in info

    missing = test_client.get("/api/chart/symbols/NOPE")
    assert missing.status_code == 404

    search = test_client.get("/api/chart/symbols", params={"query": "sp"}).json()
    assert any(item["symbol"] == "SPY" for item in search)


def test_chart_history_returns_bars_in_milliseconds() -> None:
    application = create_app()
    settings = get_settings()
    application.state.chart_service = ChartService(settings, cast(Any, FakeHistoryRegistry()))
    test_client = TestClient(application)

    response = test_client.get(
        "/api/chart/history",
        params={
            "symbol": "^GSPC",
            "resolution": "5",
            "from": 1_700_000_000,
            "to": 1_700_010_000,
            "countBack": 5,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["noData"] is False
    assert len(body["bars"]) >= 2
    assert body["bars"][0]["time"] >= 1_700_000_000_000
    assert body["source"] == "fake"


def test_chart_history_rejects_unknown_resolution() -> None:
    test_client = client()

    response = test_client.get(
        "/api/chart/history",
        params={"symbol": "^GSPC", "resolution": "7", "from": 1, "to": 2, "countBack": 5},
    )

    assert response.status_code == 400
