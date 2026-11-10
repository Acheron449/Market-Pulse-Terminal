"""Chart datafeed support (FR-28, docs/tradingview.md §4).

Serves the four endpoints the datafeed needs, from the registry and the calendar service.
Bars leave in epoch **milliseconds**; ``from``/``to`` arrive in seconds — the one deliberate
exception to the ISO-8601 rule, because these numbers go straight into the chart library.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime

from app.core.config import Settings
from app.providers.base import Bar
from app.providers.registry import AllProvidersFailed, ProviderRegistry
from app.services.market_hours import DEFAULT_CALENDAR, MarketCalendar

logger = logging.getLogger(__name__)

CURATED: dict[str, dict[str, str]] = {
    "^GSPC": {"description": "S&P 500", "exchange": "INDEX", "type": "index"},
    "^IXIC": {"description": "NASDAQ Composite", "exchange": "INDEX", "type": "index"},
    "^DJI": {"description": "Dow Jones Industrial Average", "exchange": "INDEX", "type": "index"},
    "^RUT": {"description": "Russell 2000", "exchange": "INDEX", "type": "index"},
    "^VIX": {"description": "CBOE Volatility Index", "exchange": "INDEX", "type": "index"},
    "SPY": {"description": "SPDR S&P 500 ETF Trust", "exchange": "NYSE ARCA", "type": "etf"},
    "QQQ": {"description": "Invesco QQQ Trust", "exchange": "NASDAQ", "type": "etf"},
    "DIA": {
        "description": "SPDR Dow Jones Industrial Average ETF",
        "exchange": "NYSE ARCA",
        "type": "etf",
    },
    "IWM": {"description": "iShares Russell 2000 ETF", "exchange": "NYSE ARCA", "type": "etf"},
    "VIXY": {
        "description": "ProShares VIX Short-Term Futures ETF",
        "exchange": "NYSE ARCA",
        "type": "etf",
    },
}

EXCHANGES = [
    {"value": "INDEX", "name": "Index", "desc": "Index"},
    {"value": "NASDAQ", "name": "NASDAQ", "desc": "NASDAQ"},
    {"value": "NYSE ARCA", "name": "NYSE Arca", "desc": "NYSE Arca"},
]

SYMBOL_TYPES = [
    {"name": "All types", "value": ""},
    {"name": "Index", "value": "index"},
    {"name": "Stock", "value": "stock"},
    {"name": "ETF", "value": "etf"},
]

SUBSESSIONS = [
    {"id": "regular", "description": "Regular Trading Hours", "session": "0930-1600"},
    {"id": "extended", "description": "Extended Trading Hours", "session": "0400-2000"},
    {"id": "premarket", "description": "Pre-market", "session": "0400-0930"},
    {"id": "postmarket", "description": "Post-market", "session": "1600-2000"},
]


class ChartService:
    def __init__(
        self,
        settings: Settings,
        registry: ProviderRegistry,
        calendar: MarketCalendar | None = None,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._calendar = calendar or DEFAULT_CALENDAR
        self._cache: dict[tuple[str, str, int, int], tuple[float, list[Bar]]] = {}

    # -- static configuration --------------------------------------------------
    def config(self) -> dict[str, object]:
        return {
            "supportedResolutions": self._settings.chart_resolutions,
            "exchanges": EXCHANGES,
            "symbolTypes": SYMBOL_TYPES,
            "currencyCodes": ["USD"],
            "supportsSearch": True,
            "supportsMarks": False,
            "supportsTime": True,
        }

    def search(self, query: str, movers: Sequence[str] = ()) -> list[dict[str, str]]:
        needle = query.strip().upper()
        universe = {**CURATED}
        for symbol in movers:
            universe.setdefault(
                symbol, {"description": symbol, "exchange": "NYSE ARCA", "type": "stock"}
            )
        if not needle:
            return []
        return [
            {
                "symbol": symbol,
                "ticker": symbol,
                "description": meta["description"],
                "exchange": meta["exchange"],
                "type": meta["type"],
            }
            for symbol, meta in universe.items()
            if needle in symbol or needle in meta["description"].upper()
        ]

    def symbol_info(self, symbol: str) -> dict[str, object] | None:
        meta = CURATED.get(symbol)
        if meta is None:
            return None
        today = datetime.now(UTC).date()
        is_index = meta["type"] == "index"
        delay = self._settings.alpaca_feed_delay_seconds
        return {
            "symbol": symbol,
            "ticker": symbol,
            "name": meta["description"],
            "description": meta["description"],
            "type": meta["type"],
            "listedExchange": meta["exchange"],
            "timezone": "America/New_York",
            "session": self._calendar.session_string(today),
            "subsessions": SUBSESSIONS,
            "subsessionId": "regular",
            "sessionHolidays": self._calendar.holiday_string(today.year),
            "corrections": ",".join(
                filter(
                    None,
                    [
                        self._calendar.correction_string(today),
                        self._calendar.correction_string(datetime(today.year, 11, 27).date()),
                    ],
                )
            ),
            "minmov": 1,
            "pricescale": 100,
            "minmove2": 0,
            "format": "price",
            "visiblePlotsSet": "ohlc" if is_index else "ohlcv",
            "currencyCode": "USD",
            "hasIntraday": True,
            "intradayMultipliers": ["1", "5", "15", "60"],
            "hasDaily": True,
            "dailyMultipliers": ["1"],
            "supportedResolutions": self._settings.chart_resolutions,
            "dataStatus": "streaming" if delay == 0 else "delayed_streaming",
            # Screen the replay fixture as replay, never as a live feed (AGENTS.md rule 9).
            "mode": "live" if self._settings.enable_live_data else "replay",
            "delay": delay,
            "isProxy": False,
            "source": "yfinance" if is_index else "alpaca",
            "asOf": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # -- history ---------------------------------------------------------------
    async def history(
        self, symbol: str, resolution: str, start_seconds: int, end_seconds: int, count_back: int
    ) -> dict[str, object]:
        if resolution not in self._settings.chart_resolutions:
            raise ValueError("unsupported resolution")
        start_ms, end_ms = start_seconds * 1000, end_seconds * 1000
        bars, provider = await self._bars(symbol, resolution, start_ms, end_ms)

        top_up = bars
        if len(bars) < count_back and bars:
            span = end_ms - start_ms
            wider_start = max(0, start_ms - span * max(1, count_back // max(1, len(bars))))
            older, provider = await self._bars(symbol, resolution, wider_start, start_ms)
            top_up = [*older, *bars]

        in_range = [bar for bar in top_up if start_ms <= bar.time < end_ms]
        visible = sorted(in_range, key=lambda bar: bar.time)
        if len(visible) < 2:
            visible = sorted(top_up, key=lambda bar: bar.time)[-max(2, count_back) :]
        no_data = len(visible) < 2
        return {
            "symbol": symbol,
            "resolution": resolution,
            "bars": [bar.as_dict() for bar in visible],
            "noData": no_data,
            "source": provider,
            "status": "fresh" if visible else "error",
            "asOf": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    async def _bars(
        self, symbol: str, resolution: str, start_ms: int, end_ms: int
    ) -> tuple[list[Bar], str]:
        key = (symbol, resolution, start_ms, end_ms)
        cached = self._cache.get(key)
        if (
            cached is not None
            and time.monotonic() - cached[0] < self._settings.chart_history_cache_seconds
        ):
            return cached[1], "cache"
        try:
            result = await self._registry.fetch(
                "history", "bars", symbol, resolution, start_ms, end_ms
            )
        except AllProvidersFailed:
            if cached is not None:
                return cached[1], "cache"
            raise
        bars = sorted(result.value, key=lambda bar: bar.time)
        self._cache[key] = (time.monotonic(), bars)
        return bars, result.provider

    def server_time(self) -> int:
        return int(time.time())
