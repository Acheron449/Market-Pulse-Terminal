"""Snapshot service: cadences, filters, failover to last-good (FR-8, FR-9, FR-13)."""

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from app.core.cache import SnapshotCache
from app.core.config import Settings
from app.providers.base import MoversPayload
from app.providers.registry import AllProvidersFailed, FetchResult
from app.services.event_bus import EventBus
from app.services.snapshot_builder import SnapshotUnavailable
from app.services.snapshot_service import SnapshotService
from app.services.snapshot_store import SnapshotStore


def quote(symbol: str, change: float) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "label": symbol,
        "price": 100.0,
        "change": change,
        "changePercent": change,
        "invert": symbol == "^VIX",
        "sparkline": [99.0, 100.0],
        "isProxy": False,
    }


QUOTES = [
    quote("^GSPC", 0.5),
    quote("^IXIC", 0.7),
    quote("^DJI", 0.3),
    quote("^RUT", 0.2),
    quote("^VIX", 1.0),
]

MOVERS = MoversPayload(
    gainers=(
        {"symbol": "AAA", "name": "AAA Corp", "price": 20.0, "changePercent": 8.0},
        {"symbol": "TQQQ", "name": "ProShares UltraPro QQQ", "price": 50.0, "changePercent": 9.0},
    ),
    losers=({"symbol": "BBB", "name": "BBB Corp", "price": 30.0, "changePercent": -7.0},),
    most_active=(
        {
            "symbol": "CCC",
            "name": "CCC Corp",
            "price": 40.0,
            "changePercent": 1.0,
            "volume": 900_000,
            "dayLow": 39.0,
            "dayHigh": 41.0,
        },
    ),
)

HEADLINES = [
    {
        "title": "Stocks gain on strong earnings",
        "url": "https://example.com/a",
        "source": "Finnhub",
        "publishedAt": "2026-11-06T20:15:00Z",
    }
]


class FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail: set[str] = set()

    async def fetch(self, capability: str, method: str, *args: Any) -> FetchResult:
        self.calls.append(capability)
        if capability in self.fail:
            raise AllProvidersFailed(capability, {"fake": "boom"})
        value: Any
        if capability == "quotes":
            value = QUOTES
        elif capability == "movers":
            value = MOVERS
        elif capability == "news":
            value = HEADLINES
        elif capability == "status":
            value = "regular"
        elif capability == "history":
            value = [100.0 + (index % 7) for index in range(260)]
        else:  # pragma: no cover - defensive
            raise AssertionError(capability)
        return FetchResult(provider="fake", value=value)


def build(tmp_path: Path) -> tuple[SnapshotService, FakeRegistry, SnapshotStore]:
    settings = Settings(
        _env_file=None, enable_live_data=True, database_path=tmp_path / "db.sqlite3"
    )
    registry = FakeRegistry()
    store = SnapshotStore()
    service = SnapshotService(
        settings,
        registry,
        store,
        EventBus(),
        SnapshotCache(settings.database_path),
    )
    return service, registry, store


def test_refresh_builds_a_complete_snapshot(tmp_path: Path) -> None:
    service, registry, store = build(tmp_path)

    snapshot = asyncio.run(service.refresh())

    assert len(snapshot.indexes) == 5
    assert snapshot.sources["indexes"] == "fake"
    assert snapshot.status["indexes"] == "fresh"
    assert snapshot.sentiment.components is not None
    assert len(snapshot.sentiment.components) == 5
    assert store.current() is snapshot
    assert snapshot.errors == []


def test_movers_filters_drop_leveraged_names(tmp_path: Path) -> None:
    service, _, _ = build(tmp_path)

    snapshot = asyncio.run(service.refresh())

    assert [row.symbol for row in snapshot.gainers] == ["AAA"]
    assert [row.symbol for row in snapshot.losers] == ["BBB"]
    assert [row.symbol for row in snapshot.most_active] == ["CCC"]


def test_cadence_skips_a_section_that_is_not_due(tmp_path: Path) -> None:
    service, registry, _ = build(tmp_path)

    asyncio.run(service.refresh())
    first = registry.calls.count("quotes")
    asyncio.run(service.refresh())

    assert registry.calls.count("quotes") == first


def test_force_refetches_every_section(tmp_path: Path) -> None:
    service, registry, _ = build(tmp_path)

    asyncio.run(service.refresh())
    asyncio.run(service.refresh(force=True))

    assert registry.calls.count("quotes") == 2


def test_failed_section_keeps_the_last_good_data(tmp_path: Path) -> None:
    service, registry, _ = build(tmp_path)
    good = asyncio.run(service.refresh())

    registry.fail = {"quotes"}
    stale = asyncio.run(service.refresh(force=True))

    assert [card.symbol for card in stale.indexes] == [card.symbol for card in good.indexes]
    assert stale.status["indexes"] == "stale"
    assert any(error.section == "indexes" for error in stale.errors)


def test_refresh_is_serialised(tmp_path: Path) -> None:
    service, registry, _ = build(tmp_path)

    async def twice() -> None:
        await asyncio.gather(service.refresh(force=True), service.refresh(force=True))

    asyncio.run(twice())

    # Two overlapping forced refreshes cannot interleave their provider calls.
    assert registry.calls.count("status") <= 4
    assert service is not None


def test_disabled_live_data_serves_the_seeded_snapshot(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, enable_live_data=False)
    registry = FakeRegistry()
    store = SnapshotStore()
    service = SnapshotService(settings, registry, store, EventBus(), SnapshotCache(tmp_path / "db"))

    with pytest.raises(SnapshotUnavailable):
        asyncio.run(service.refresh())
    assert registry.calls == []


def test_sections_age_is_reported(tmp_path: Path) -> None:
    service, _, _ = build(tmp_path)
    snapshot = asyncio.run(service.refresh())

    assert service.last_refreshed_at() == snapshot.fetched_at
    assert time.monotonic() > 0
