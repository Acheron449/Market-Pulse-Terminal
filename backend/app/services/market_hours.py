"""US market calendar and status derivation (SRS §9, docs/tradingview.md §6).

Alpaca's clock is the primary source, but the app must still know whether the market is
open when that call fails, so the rules are implemented here and used as the last-resort
provider. Holidays are computed from the NYSE rules rather than hand-maintained date lists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.models import MarketStatus

EASTERN = ZoneInfo("America/New_York")

REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
PREMARKET_OPEN = time(4, 0)
AFTER_HOURS_CLOSE = time(20, 0)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The nth given weekday of a month (Monday=0), e.g. the 4th Thursday of November."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    last = next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm, needed for Good Friday."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    shift = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * shift) // 451
    month, day = divmod(h + shift - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed(day: date) -> date:
    """NYSE observance: a Saturday holiday moves to Friday, a Sunday one to Monday."""
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def market_holidays(year: int) -> frozenset[date]:
    """Full-day NYSE closures for a calendar year."""
    holidays = {
        _observed(date(year, 1, 1)),  # New Year's Day
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
        easter_sunday(year) - timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed(date(year, 6, 19)),  # Juneteenth
        _observed(date(year, 7, 4)),  # Independence Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),  # Christmas
    }
    return frozenset(holidays)


def early_closes(year: int) -> dict[date, time]:
    """13:00 ET closes: the Friday after Thanksgiving and Christmas Eve when a weekday."""
    closes: dict[date, time] = {}
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    closes[thanksgiving + timedelta(days=1)] = time(13, 0)
    christmas_eve = date(year, 12, 24)
    if christmas_eve.weekday() < 5 and christmas_eve not in market_holidays(year):
        closes[christmas_eve] = time(13, 0)
    return closes


@dataclass(frozen=True, slots=True)
class MarketCalendar:
    """Calendar rules with a per-year cache. Pure: no clock, no network."""

    _holidays: dict[int, frozenset[date]] = field(default_factory=dict)
    _early: dict[int, dict[date, time]] = field(default_factory=dict)

    def holidays(self, year: int) -> frozenset[date]:
        return self._holidays.setdefault(year, market_holidays(year))

    def early_close(self, day: date) -> time | None:
        closes = self._early.setdefault(day.year, early_closes(day.year))
        return closes.get(day)

    def is_trading_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.holidays(day.year)

    def close_time(self, day: date) -> time:
        return self.early_close(day) or REGULAR_CLOSE

    def status(self, now: datetime) -> MarketStatus:
        """Map an aware UTC instant onto the contract's marketStatus enum."""
        if now.tzinfo is None:
            raise ValueError("market status needs a timezone-aware instant")
        eastern = now.astimezone(EASTERN)
        day = eastern.date()
        if not self.is_trading_day(day):
            return "closed"
        current = eastern.time()
        if PREMARKET_OPEN <= current < REGULAR_OPEN:
            return "pre_market"
        if REGULAR_OPEN <= current < self.close_time(day):
            return "regular"
        if self.close_time(day) <= current < AFTER_HOURS_CLOSE:
            return "after_hours"
        return "closed"

    def session_string(self, day: date) -> str:
        close = self.close_time(day)
        return f"{REGULAR_OPEN:%H%M}-{close:%H%M}"

    def correction_string(self, day: date) -> str | None:
        close = self.early_close(day)
        if close is None:
            return None
        return f"{REGULAR_OPEN:%H%M}-{close:%H%M}:{day:%Y%m%d}"

    def holiday_string(self, year: int) -> str:
        return ",".join(sorted(f"{day:%Y%m%d}" for day in self.holidays(year)))


DEFAULT_CALENDAR = MarketCalendar()


def normalize_market_status(value: str) -> MarketStatus:
    """Narrow a provider string onto the contract enum, falling back to ``unknown``."""
    allowed: tuple[MarketStatus, ...] = (
        "pre_market",
        "regular",
        "after_hours",
        "closed",
        "unknown",
    )
    for candidate in allowed:
        if value == candidate:
            return candidate
    return "unknown"


def cadences_for(settings: Settings, status: MarketStatus) -> dict[str, int]:
    """Per-section refresh cadence for a market state (SRS §9)."""
    suffix = {
        "regular": "",
        "pre_market": "_offhours",
        "after_hours": "_offhours",
        "closed": "_closed",
        "unknown": "_offhours",
    }[status]
    return {
        "quotes": int(getattr(settings, f"quotes_refresh_seconds{suffix}")),
        "movers": int(getattr(settings, f"movers_refresh_seconds{suffix}")),
        "news": int(getattr(settings, f"news_refresh_seconds{suffix}")),
        "status": settings.status_refresh_seconds,
        "history": settings.history_refresh_seconds,
    }
