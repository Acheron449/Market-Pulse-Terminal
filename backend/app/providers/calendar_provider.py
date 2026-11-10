"""Bundled NYSE calendar as the last-resort market-status provider (SRS §4.1).

Alpaca's clock and Finnhub's market-status come first; this adapter keeps the status chip
honest when both are down or unconfigured, and it is what supplies sessions, holidays and
early-close corrections to the chart endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.providers.base import Capability, MarketDataProvider
from app.services.market_hours import DEFAULT_CALENDAR, MarketCalendar


class CalendarProvider(MarketDataProvider):
    name = "calendar"
    capabilities: frozenset[Capability] = frozenset({"status"})

    def __init__(self, calendar: MarketCalendar | None = None) -> None:
        self._calendar = calendar or DEFAULT_CALENDAR

    def is_configured(self) -> bool:
        return True

    async def market_status(self) -> str:
        return self._calendar.status(datetime.now(UTC))
