"""Provider wiring: one place that knows which adapters exist (`AGENTS.md` §11)."""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from app.core.config import Settings
from app.providers.alpaca_provider import AlpacaProvider
from app.providers.base import MarketDataProvider
from app.providers.calendar_provider import CalendarProvider
from app.providers.finnhub_provider import FinnhubProvider
from app.providers.registry import ProviderRegistry
from app.providers.yfinance_provider import YFinanceProvider
from app.services.market_hours import DEFAULT_CALENDAR, MarketCalendar


def build_providers(
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
    calendar: MarketCalendar | None = None,
) -> Sequence[MarketDataProvider]:
    """Every adapter, configured or not: the registry skips what it cannot use."""
    return [
        YFinanceProvider(settings),
        AlpacaProvider(settings, client=client),
        FinnhubProvider(settings, client=client),
        CalendarProvider(calendar or DEFAULT_CALENDAR),
    ]


def build_registry(
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
    calendar: MarketCalendar | None = None,
) -> ProviderRegistry:
    return ProviderRegistry(build_providers(settings, client=client, calendar=calendar), settings)
