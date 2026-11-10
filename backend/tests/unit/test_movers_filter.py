"""Movers filters (FR-7)."""

from app.services.movers_filter import (
    MoverFilters,
    apply_filters,
    is_leveraged,
    is_warrant_or_right,
)


def row(symbol: str, price: float = 25.0, name: str = "Example Corp", volume: float = 500_000):
    return {
        "symbol": symbol,
        "name": name,
        "price": price,
        "changePercent": 5.0,
        "volume": volume,
        "dayLow": price - 1,
        "dayHigh": price + 1,
    }


def test_penny_stocks_are_dropped() -> None:
    filtered = apply_filters(
        gainers=[row("PENNY", price=0.4), row("FINE", price=12.0)],
        losers=[],
        most_active=[],
        filters=MoverFilters(min_price=1.0),
    )

    assert [item["symbol"] for item in filtered.gainers] == ["FINE"]
    assert filtered.dropped == 1


def test_warrants_and_rights_are_dropped() -> None:
    assert is_warrant_or_right("ABCDW")
    assert is_warrant_or_right("ABCD.RT")
    assert not is_warrant_or_right("AAPL")

    filtered = apply_filters(
        gainers=[row("ABCDW"), row("AAPL")],
        losers=[],
        most_active=[],
        filters=MoverFilters(exclude_warrants=True),
    )

    assert [item["symbol"] for item in filtered.gainers] == ["AAPL"]


def test_leveraged_etfs_are_dropped_when_configured() -> None:
    assert is_leveraged("TQQQ")
    assert is_leveraged("XYZ", "ProShares UltraPro S&P 500")

    filtered = apply_filters(
        gainers=[row("TQQQ", name="ProShares UltraPro QQQ"), row("MSFT")],
        losers=[],
        most_active=[],
        filters=MoverFilters(exclude_leveraged_etfs=True),
    )
    assert [item["symbol"] for item in filtered.gainers] == ["MSFT"]

    kept = apply_filters(
        gainers=[row("TQQQ")],
        losers=[],
        most_active=[],
        filters=MoverFilters(exclude_leveraged_etfs=False),
    )
    assert [item["symbol"] for item in kept.gainers] == ["TQQQ"]


def test_most_active_requires_minimum_volume() -> None:
    filtered = apply_filters(
        gainers=[],
        losers=[],
        most_active=[row("THIN", volume=1_000), row("THICK", volume=5_000_000)],
        filters=MoverFilters(min_volume=100_000),
    )

    assert [item["symbol"] for item in filtered.most_active] == ["THICK"]


def test_gainers_and_losers_do_not_need_volume() -> None:
    filtered = apply_filters(
        gainers=[row("A", volume=0)],
        losers=[row("B", volume=0)],
        most_active=[],
        filters=MoverFilters(min_volume=100_000),
    )

    assert len(filtered.gainers) == 1
    assert len(filtered.losers) == 1
