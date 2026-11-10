"""Snapshot orchestration: registry -> sections -> builder -> store/bus/cache (FR-8, FR-9).

One ``refresh`` cycle fetches every section through the registry, respects each section's
cadence (SRS §9), computes the mood, builds the contract snapshot and publishes it. No
provider is touched directly, and a failed section falls through to the builder's
last-good retention instead of blanking the dashboard.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.cache import SnapshotCache
from app.core.config import Settings
from app.models import MarketSnapshot, MarketStatus, SnapshotError
from app.providers.base import MoversPayload, Row
from app.providers.registry import AllProvidersFailed, FetchResult, ProviderRegistry
from app.services.event_bus import EventBus
from app.services.market_hours import (
    DEFAULT_CALENDAR,
    MarketCalendar,
    cadences_for,
    normalize_market_status,
)
from app.services.movers_filter import MoverFilters, apply_filters
from app.services.sentiment import (
    MoodInputs,
    compute_mood,
    distance_from_average,
    percentile_of_last,
)
from app.services.snapshot_builder import (
    MoversResult,
    SectionResult,
    SentimentInput,
    SnapshotInputs,
    SnapshotUnavailable,
    build_snapshot,
)
from app.services.snapshot_store import SnapshotStore
from app.services.static_export import export_snapshot

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _Section:
    """Rows kept between cycles so a section is only refetched when its cadence is due."""

    rows: list[Row] = field(default_factory=list)
    provider: str = ""
    delay_seconds: int = 0
    fetched_at: float = 0.0
    ok: bool = True


class SnapshotService:
    """Owns the refresh cycle and the section cadences."""

    def __init__(
        self,
        settings: Settings,
        registry: ProviderRegistry,
        store: SnapshotStore,
        bus: EventBus,
        cache: SnapshotCache,
        calendar: MarketCalendar | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._store = store
        self._bus = bus
        self._cache = cache
        self._calendar = calendar or DEFAULT_CALENDAR
        self._clock = clock
        self._sections: dict[str, _Section] = {}
        self._movers = MoversPayload()
        self._history: dict[str, tuple[float, list[float]]] = {}
        self._lock = asyncio.Lock()

    # -- public API ------------------------------------------------------------
    async def refresh(self, *, force: bool = False) -> MarketSnapshot:
        """Build a new snapshot. Overlapping calls wait rather than double-fetch."""
        if not self._settings.enable_live_data:
            # Offline/demo mode: serve the seeded recording untouched (AGENTS.md rule 9).
            current = self._store.current()
            if current is None:
                raise SnapshotUnavailable("live data is disabled and no snapshot is seeded")
            return current

        async with self._lock:
            return await self._refresh(force=force)

    def current(self) -> MarketSnapshot | None:
        return self._store.current()

    def market_status(self) -> MarketStatus:
        current = self._store.current()
        return current.sentiment.market_status if current is not None else "unknown"

    def last_refreshed_at(self) -> str | None:
        snapshot = self._store.current()
        return snapshot.fetched_at if snapshot is not None else None

    # -- the cycle -------------------------------------------------------------
    async def _refresh(self, *, force: bool) -> MarketSnapshot:
        now = datetime.now(UTC)
        status, status_provider = await self._market_status(now)
        cadence = cadences_for(self._settings, status)
        previous = self._store.current()
        errors: list[SnapshotError] = []

        quotes = await self._section(
            "quotes", cadence["quotes"], force, self._fetch_quotes, previous, errors
        )
        movers = await self._section(
            "movers", cadence["movers"], force, self._fetch_movers, previous, errors
        )
        news = await self._section(
            "news", cadence["news"], force, self._fetch_news, previous, errors
        )

        filtered = apply_filters(
            gainers=self._movers.gainers,
            losers=self._movers.losers,
            most_active=self._movers.most_active,
            filters=MoverFilters(
                min_price=self._settings.movers_min_price,
                min_volume=self._settings.movers_min_volume,
                exclude_warrants=self._settings.movers_exclude_warrants,
                exclude_leveraged_etfs=self._settings.movers_exclude_leveraged_etfs,
            ),
        )

        sentiment = await self._mood(status, quotes.rows, news.rows, cadence["history"])

        snapshot = build_snapshot(
            SnapshotInputs(
                fetched_at=now,
                market_status=status,
                market_status_provider=status_provider,
                indexes=SectionResult(
                    provider=quotes.provider or "unknown",
                    rows=tuple(quotes.rows),
                    delay_seconds=quotes.delay_seconds,
                ),
                movers=MoversResult(
                    provider=movers.provider or "unknown",
                    gainers=filtered.gainers,
                    losers=filtered.losers,
                    most_active=filtered.most_active,
                    delay_seconds=movers.delay_seconds,
                ),
                news=SectionResult(
                    provider=news.provider or "unknown",
                    rows=tuple(news.rows),
                    delay_seconds=news.delay_seconds,
                ),
                sentiment=sentiment,
                previous=previous,
            )
        )

        self._store.replace(snapshot)
        self._bus.publish(snapshot)
        try:
            await self._cache.save(snapshot)
            if self._settings.enable_static_export:
                await export_snapshot(self._settings.static_export_path, snapshot)
        except OSError as exc:  # pragma: no cover - disk problems must not stop the feed
            logger.warning("could not persist snapshot: %s", exc)
        return snapshot

    # -- sections --------------------------------------------------------------
    async def _section(
        self,
        name: str,
        ttl: int,
        force: bool,
        fetcher: Callable[[], Awaitable[FetchResult]],
        previous: MarketSnapshot | None,
        errors: list[SnapshotError],
    ) -> _Section:
        cached = self._sections.get(name)
        if cached is not None and not force and self._clock() - cached.fetched_at < ttl:
            return cached

        try:
            result = await fetcher()
        except AllProvidersFailed as exc:
            # Keep the last good rows for the builder to serve as `stale` (FR-9).
            if name == "movers":
                self._movers = MoversPayload()
            provider = previous.sources.get(name, "") if previous else ""
            errors.append(
                SnapshotError(section=name, provider=provider or None, message=str(exc)[:180])
            )
            logger.warning("section %s failed: %s", name, exc)
            return _Section(rows=[], provider=provider, fetched_at=self._clock(), ok=False)

        section = _Section(
            rows=list(result.value) if isinstance(result.value, list) else [],
            provider=result.provider,
            delay_seconds=self._delay_for(result.provider),
            fetched_at=self._clock(),
        )
        self._sections[name] = section
        return section

    def _delay_for(self, provider: str) -> int:
        """Feed delay per provider, from the disclosure table (provider-notes §6)."""
        if provider == "alpaca":
            return self._settings.alpaca_feed_delay_seconds
        if provider == "yfinance":
            return 900
        return 0

    async def _fetch_quotes(self) -> FetchResult:
        return await self._registry.fetch("quotes", "quotes", self._settings.index_symbols)

    async def _fetch_movers(self) -> FetchResult:
        result = await self._registry.fetch("movers", "movers")
        payload = result.value
        if isinstance(payload, MoversPayload):
            self._movers = payload
            return FetchResult(
                provider=result.provider,
                value=[*payload.gainers, *payload.losers, *payload.most_active],
            )
        return result

    async def _fetch_news(self) -> FetchResult:
        return await self._registry.fetch("news", "news", 5)

    # -- status ----------------------------------------------------------------
    async def _market_status(self, now: datetime) -> tuple[MarketStatus, str]:
        local = self._calendar.status(now)
        try:
            result = await self._registry.fetch("status", "market_status")
        except AllProvidersFailed:
            return local, "calendar"
        reported = normalize_market_status(str(result.value))
        if reported == "regular":
            return "regular", result.provider
        # A "closed" answer cannot tell pre-market from after-hours; the calendar can.
        return local, result.provider

    # -- mood ------------------------------------------------------------------
    async def _mood(
        self, status: MarketStatus, quotes: list[Row], headlines: list[Row], history_ttl: int
    ) -> SentimentInput | None:
        changes = {
            str(row.get("symbol")): float(row["changePercent"])
            for row in quotes
            if isinstance(row.get("changePercent"), (int, float))
        }
        vix_closes = await self._closes("^VIX", 260, history_ttl)
        spx_closes = await self._closes("^GSPC", 60, history_ttl)

        mood = compute_mood(
            MoodInputs(
                market_status=status,
                index_changes=changes,
                vix_percentile=percentile_of_last(vix_closes) if vix_closes else None,
                vix_change_percent=changes.get("^VIX"),
                spx_distance_from_sma_percent=(
                    distance_from_average(spx_closes, 50) if spx_closes else None
                ),
                headlines=headlines,
            ),
            weights=self._settings.sentiment_weights,  # type: ignore[arg-type]
            bands=self._settings.sentiment_bands,
            min_components=self._settings.sentiment_min_components,
            headline_tone_enabled=self._settings.enable_headline_tone,
        )
        if mood.available == 0:
            return None
        return SentimentInput(
            verdict=mood.verdict,
            position=mood.position,
            components=tuple(mood.component_payload),
            summary=mood.summary,
        )

    async def _closes(self, symbol: str, days: int, ttl: int) -> list[float]:
        cached = self._history.get(symbol)
        if cached is not None and self._clock() - cached[0] < ttl:
            return cached[1]
        try:
            result = await self._registry.fetch("history", "daily_closes", symbol, days)
        except AllProvidersFailed:
            return cached[1] if cached else []
        closes = [float(value) for value in result.value]
        self._history[symbol] = (self._clock(), closes)
        return closes
