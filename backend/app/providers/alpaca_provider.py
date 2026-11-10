"""Alpaca adapter: IEX quotes via proxy ETFs, screener, clock, news and bars.

Free Alpaca equity feeds carry no index levels, so ``quotes`` maps each index onto its
documented proxy ETF and flags it ``isProxy`` (`AGENTS.md` rule 7): the card shows SPY, not
a pretend S&P 500 level.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import Settings
from app.providers.base import (
    Bar,
    Capability,
    MarketDataProvider,
    MoversPayload,
    ProviderError,
    Row,
)

logger = logging.getLogger(__name__)

DATA_URL = "https://data.alpaca.markets"
API_URL = "https://api.alpaca.markets"

#: Index symbol -> (proxy ETF, display label).
PROXIES: dict[str, tuple[str, str]] = {
    "^GSPC": ("SPY", "SPY (S&P 500 proxy)"),
    "^IXIC": ("QQQ", "QQQ (NASDAQ proxy)"),
    "^DJI": ("DIA", "DIA (Dow proxy)"),
    "^RUT": ("IWM", "IWM (Russell 2000 proxy)"),
    "^VIX": ("VIXY", "VIXY (VIX proxy)"),
}

RESOLUTION_TO_TIMEFRAME = {"1": "1Min", "5": "5Min", "15": "15Min", "60": "1Hour", "1D": "1Day"}


class AlpacaProvider(MarketDataProvider):
    """REST client with explicit timeouts (SRS §7.3)."""

    name = "alpaca"
    capabilities: frozenset[Capability] = frozenset(
        {"quotes", "movers", "status", "news", "history"}
    )

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client
        self._sparkline_points = settings.sparkline_points

    def is_configured(self) -> bool:
        return self._settings.alpaca_configured

    # -- plumbing --------------------------------------------------------------
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    self._settings.http_timeout_seconds,
                    connect=self._settings.http_connect_timeout_seconds,
                ),
                headers={
                    "APCA-API-KEY-ID": self._settings.alpaca_api_key or "",
                    "APCA-API-SECRET-KEY": self._settings.alpaca_api_secret or "",
                },
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, base: str, path: str, params: dict[str, Any]) -> Any:
        try:
            response = await self._http().get(f"{base}{path}", params=params)
        except httpx.HTTPError as exc:
            # The exception text can contain the URL; only the class name is recorded.
            raise ProviderError(self.name, "http", type(exc).__name__) from exc
        if response.status_code == 429:
            raise ProviderError(self.name, "http", "429 rate limited")
        if response.status_code >= 400:
            raise ProviderError(self.name, "http", f"HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(self.name, "http", "malformed json") from exc

    # -- quotes ----------------------------------------------------------------
    async def quotes(self, symbols: Sequence[str]) -> list[Row]:
        rows: list[Row] = []
        for symbol in symbols:
            proxy, label = PROXIES.get(symbol, (symbol, symbol.lstrip("^")))
            bars = await self._bars(proxy, "5Min", limit=self._sparkline_points)
            if not bars:
                continue
            price = bars[-1]["close"]
            reference = bars[0]["open"] or price
            if reference <= 0 or price <= 0:
                continue
            change = price - reference
            rows.append(
                {
                    "symbol": proxy,
                    "label": label,
                    "price": price,
                    "change": round(change, 4),
                    "changePercent": round(change / reference * 100, 4),
                    "invert": symbol == "^VIX",
                    "sparkline": [bar["close"] for bar in bars],
                    "isProxy": True,
                    "asOf": _iso(datetime.now(UTC)),
                }
            )
        if not rows:
            raise ProviderError(self.name, "quotes", "no usable quotes")
        return rows

    # -- movers ----------------------------------------------------------------
    async def movers(self) -> MoversPayload:
        payload = await self._get(DATA_URL, "/v1beta1/screener/stocks/movers", {"top": 25})
        gainers = [_mover_row(item) for item in payload.get("gainers", [])]
        losers = [_mover_row(item) for item in payload.get("losers", [])]

        active_payload = await self._get(
            DATA_URL, "/v1beta1/screener/stocks/most-actives", {"top": 25, "by": "volume"}
        )
        active_symbols = [
            str(item.get("symbol", ""))
            for item in active_payload.get("most_actives", [])
            if item.get("symbol")
        ]
        active: list[Row] = []
        if active_symbols:
            snapshots = await self._get(
                DATA_URL, "/v2/stocks/snapshots", {"symbols": ",".join(active_symbols[:25])}
            )
            for symbol in active_symbols:
                snapshot = snapshots.get(symbol) if isinstance(snapshots, dict) else None
                row = _snapshot_row(symbol, snapshot)
                if row is not None:
                    active.append(row)

        if not (gainers or losers or active):
            raise ProviderError(self.name, "movers", "screener returned nothing")
        return MoversPayload(
            gainers=tuple(gainers), losers=tuple(losers), most_active=tuple(active)
        )

    # -- status ----------------------------------------------------------------
    async def market_status(self) -> str:
        payload = await self._get(API_URL, "/v2/clock", {})
        return "regular" if payload.get("is_open") else "closed"

    # -- news ------------------------------------------------------------------
    async def news(self, limit: int) -> list[Row]:
        payload = await self._get(
            DATA_URL, "/v1beta1/news", {"limit": limit, "exclude_content": "true"}
        )
        rows: list[Row] = []
        for item in payload if isinstance(payload, list) else payload.get("news", []):
            url = str(item.get("url", ""))
            title = str(item.get("headline", ""))
            if not title or not url.startswith("http"):
                continue
            rows.append(
                {
                    "title": title,
                    "url": url,
                    "source": str(item.get("source") or "Alpaca"),
                    "publishedAt": _iso_epoch(item.get("created_at")),
                }
            )
        if not rows:
            raise ProviderError(self.name, "news", "no usable headlines")
        return rows[:limit]

    # -- history ---------------------------------------------------------------
    async def daily_closes(self, symbol: str, days: int) -> list[float]:
        bars = await self._bars(symbol, "1Day", limit=days)
        closes = [bar["close"] for bar in bars]
        if not closes:
            raise ProviderError(self.name, "history", "no closes")
        return closes

    async def bars(self, symbol: str, resolution: str, start_ms: int, end_ms: int) -> list[Bar]:
        timeframe = RESOLUTION_TO_TIMEFRAME.get(resolution)
        if timeframe is None:
            raise ProviderError(self.name, "history", "unsupported resolution")
        payload = await self._get(
            DATA_URL,
            "/v2/stocks/bars",
            {
                "symbols": symbol,
                "timeframe": timeframe,
                "start": _rfc3339(start_ms),
                "end": _rfc3339(end_ms),
                "limit": 10_000,
                "adjustment": "raw",
                "feed": self._settings.alpaca_feed,
            },
        )
        bars = payload.get("bars", {}).get(symbol, []) if isinstance(payload, dict) else []
        result: list[Bar] = []
        for item in bars:
            opened = _number(item.get("o"))
            high = _number(item.get("h"))
            low = _number(item.get("l"))
            close = _number(item.get("c"))
            if None in (opened, high, low, close):
                continue
            moment = datetime.fromisoformat(str(item["t"]).replace("Z", "+00:00"))
            result.append(
                Bar(
                    time=int(moment.timestamp() * 1000),
                    open=float(opened),  # type: ignore[arg-type]
                    high=float(high),  # type: ignore[arg-type]
                    low=float(low),  # type: ignore[arg-type]
                    close=float(close),  # type: ignore[arg-type]
                    volume=_number(item.get("v")),
                )
            )
        if not result:
            raise ProviderError(self.name, "history", "no bars")
        return result

    async def _bars(self, symbol: str, timeframe: str, *, limit: int) -> list[dict[str, float]]:
        start = datetime.now(UTC) - timedelta(days=2)
        payload = await self._get(
            DATA_URL,
            "/v2/stocks/bars",
            {
                "symbols": symbol,
                "timeframe": timeframe,
                "limit": limit,
                "start": _rfc3339(int(start.timestamp() * 1000)),
                "adjustment": "raw",
                "feed": self._settings.alpaca_feed,
            },
        )
        rows = payload.get("bars", {}).get(symbol, []) if isinstance(payload, dict) else []
        result: list[dict[str, float]] = []
        for item in rows:
            close = item.get("c")
            opened = item.get("o")
            if not isinstance(close, (int, float)) or not isinstance(opened, (int, float)):
                continue
            result.append({"close": float(close), "open": float(opened)})
        return result


def _mover_row(item: dict[str, Any]) -> Row:
    symbol = str(item.get("symbol", ""))
    return {
        "symbol": symbol,
        "name": str(item.get("name") or symbol),
        "price": float(item.get("price") or 0),
        "changePercent": float(item.get("percent_change") or 0),
    }


def _snapshot_row(symbol: str, snapshot: Any) -> Row | None:
    if not isinstance(snapshot, dict):
        return None
    trade = snapshot.get("latestTrade") or {}
    daily = snapshot.get("dailyBar") or {}
    previous = snapshot.get("prevDailyBar") or {}
    price = trade.get("p") or daily.get("c")
    previous_close = previous.get("c")
    low = daily.get("l")
    high = daily.get("h")
    volume = daily.get("v")
    if not isinstance(price, (int, float)) or not isinstance(low, (int, float)):
        return None
    if not isinstance(high, (int, float)) or not isinstance(volume, (int, float)):
        return None
    change_percent = 0.0
    if isinstance(previous_close, (int, float)) and previous_close > 0:
        change_percent = (float(price) - float(previous_close)) / float(previous_close) * 100
    return {
        "symbol": symbol,
        "name": symbol,
        "price": float(price),
        "changePercent": round(change_percent, 4),
        "volume": float(volume),
        "dayLow": float(low),
        "dayHigh": float(high),
    }


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_epoch(value: Any) -> str:
    """Alpaca news timestamps are RFC 3339 strings; accept them and pass through."""
    text = str(value or "")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return _iso(datetime.now(UTC))
    return _iso(parsed)


def _rfc3339(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
