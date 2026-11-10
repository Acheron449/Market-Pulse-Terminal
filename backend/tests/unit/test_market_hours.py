"""Market calendar and status derivation (SRS §9)."""

from datetime import UTC, date, datetime

import pytest

from app.services.market_hours import (
    DEFAULT_CALENDAR,
    cadences_for,
    early_closes,
    market_holidays,
    normalize_market_status,
)


def status(year: int, month: int, day: int, hour: int, minute: int = 0) -> str:
    return DEFAULT_CALENDAR.status(datetime(year, month, day, hour, minute, tzinfo=UTC))


def test_regular_pre_and_after_hours() -> None:
    # 2026-11-25 is a Wednesday, EST (UTC-5).
    assert status(2026, 11, 25, 13, 0) == "pre_market"  # 08:00 ET
    assert status(2026, 11, 25, 14, 45) == "regular"  # 09:45 ET
    assert status(2026, 11, 25, 21, 30) == "after_hours"  # 16:30 ET
    assert status(2026, 11, 25, 2, 0) == "closed"  # 21:00 ET the previous day


def test_thanksgiving_is_closed() -> None:
    assert status(2026, 11, 26, 15, 0) == "closed"


def test_half_day_closes_at_13() -> None:
    assert status(2026, 11, 27, 17, 30) == "regular"  # 12:30 ET
    assert status(2026, 11, 27, 18, 30) == "after_hours"  # 13:30 ET
    assert DEFAULT_CALENDAR.session_string(date(2026, 11, 27)) == "0930-1300"


def test_weekends_and_holidays_are_closed() -> None:
    assert status(2026, 11, 28, 15, 0) == "closed"  # Saturday
    assert status(2026, 7, 3, 15, 0) == "closed"  # July 4 observed on Friday
    assert status(2027, 1, 1, 15, 0) == "closed"  # New Year's Day
    assert status(2026, 12, 25, 15, 0) == "closed"  # Christmas


def test_holiday_rules_cover_the_year() -> None:
    holidays = market_holidays(2026)
    assert date(2026, 4, 3) in holidays  # Good Friday
    assert date(2026, 11, 26) in holidays
    assert date(2026, 7, 3) in holidays  # observed Independence Day
    assert len(holidays) == 10


def test_christmas_eve_is_an_early_close() -> None:
    closes = early_closes(2026)
    assert date(2026, 12, 24) in closes
    assert closes[date(2026, 12, 24)].hour == 13


def test_correction_string_and_normalisation() -> None:
    assert DEFAULT_CALENDAR.correction_string(date(2026, 11, 27)) == "0930-1300:20261127"
    assert normalize_market_status("regular") == "regular"
    assert normalize_market_status("nonsense") == "unknown"
    assert DEFAULT_CALENDAR.holiday_string(2026).startswith("20260101")


def test_cadences_follow_the_market_state() -> None:
    from app.core.config import Settings

    settings = Settings(_env_file=None)
    assert cadences_for(settings, "regular")["quotes"] == settings.quotes_refresh_seconds
    assert cadences_for(settings, "closed")["quotes"] == settings.quotes_refresh_seconds_closed
    assert cadences_for(settings, "closed")["movers"] > cadences_for(settings, "regular")["movers"]


def test_naive_instant_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        DEFAULT_CALENDAR.status(datetime(2026, 11, 25, 15, 0))
