"""Finnhub adapter: quotes (proxy ETFs), market status and general market news.

The free tier is real-time for US quotes but has no index levels and no working candle
endpoint on many keys, so this adapter never asks for candles. News is the section it
exists for (`docs/provider-notes.md` §1).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.providers.base import Capability, MarketDataProvider, ProviderError, Row

logger = logging.getLogger(__name__)

BASE_URL = "https://finnhub.io/api/v1"

PROXIES: dict[str, tuple[str, str]] = {
    "^GSPC": ("SPY", "SPY (S&P 500 proxy)"),
    "^IXIC": ("QQQ", "QQQ (NASDAQ proxy)"),
    "^DJI": ("DIA", "DIA (Dow proxy)"),
    "^RUT": ("IWM", "IWM (Russell 2000 proxy)"),
    "^VIX": ("VIXY", "VIXY (VIX proxy)"),
}


class FinnhubProvider(MarketDataProvider):
    """REST client for the free tier, kept under one call per second by the registry."""

    name = "finnhub"
    capabilities: frozenset[Capability] = frozenset({"quotes", "status", "news"})

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def is_configured(self) -> bool:
        return self._settings.finnhub_configured

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    self._settings.http_timeout_seconds,
                    connect=self._settings.http_connect_timeout_seconds,
                )
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        params = {**params, "token": self._settings.finnhub_api_key or ""}
        try:
            response = await self._http().get(f"{BASE_URL}{path}", params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, "http", type(exc).__name__) from exc
        if response.status_code == 429:
            raise ProviderError(self.name, "http", "429 rate limited")
        if response.status_code >= 400:
            raise ProviderError(self.name, "http", f"HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(self.name, "http", "malformed json") from exc

    async def quotes(self, symbols: Sequence[str]) -> list[Row]:
        rows: list[Row] = []
        for symbol in symbols:
            proxy, label = PROXIES.get(symbol, (symbol, symbol.lstrip("^")))
            payload = await self._get("/quote", {"symbol": proxy})
            price = payload.get("c")
            previous_close = payload.get("pc")
            if not isinstance(price, (int, float)) or price <= 0:
                continue
            if not isinstance(previous_close, (int, float)) or previous_close <= 0:
                continue
            change = float(price) - float(previous_close)
            rows.append(
                {
                    "symbol": proxy,
                    "label": label,
                    "price": float(price),
                    "change": round(change, 4),
                    "changePercent": round(change / float(previous_close) * 100, 4),
                    "invert": symbol == "^VIX",
                    # Only open/previous close/high/low are available: a short, honest line.
                    "sparkline": [float(payload.get("o") or price), float(price)],
                    "isProxy": True,
                    "asOf": _iso_now(),
                }
            )
        if not rows:
            raise ProviderError(self.name, "quotes", "no usable quotes")
        return rows

    async def market_status(self) -> str:
        payload = await self._get("/stock/market-status", {"exchange": "US"})
        return "regular" if payload.get("isOpen") else "closed"

    async def news(self, limit: int) -> list[Row]:
        payload = await self._get("/news", {"category": "general"})
        rows: list[Row] = []
        for item in payload if isinstance(payload, list) else []:
            title = str(item.get("headline", ""))
            url = str(item.get("url", ""))
            if not title or not url.startswith("http"):
                continue
            rows.append(
                {
                    "title": title,
                    "url": url,
                    "source": str(item.get("source") or "Finnhub"),
                    "publishedAt": _iso_epoch(item.get("datetime")),
                }
            )
        if not rows:
            raise ProviderError(self.name, "news", "no usable headlines")
        return rows[:limit]


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_epoch(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OSError):
        return _iso_now()
