"""Snapshot builder rules: validation, last-good retention, provenance (FR-5/6/8/9)."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from app.models import MarketSnapshot
from app.services.snapshot_builder import (
    MoversResult,
    SectionResult,
    SentimentInput,
    SnapshotInputs,
    SnapshotUnavailable,
    build_snapshot,
)


def quote(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "symbol": "^GSPC",
        "label": "S&P 500",
        "price": 7475.46,
        "change": -25.12,
        "changePercent": -0.33,
        "invert": False,
        "sparkline": [7500.58, 7475.46],
        "isProxy": False,
    }
    row.update(overrides)
    return row


def mover(symbol: str = "NVDA", **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "symbol": symbol,
        "name": "NVIDIA Corp.",
        "price": 188.42,
        "changePercent": 6.12,
    }
    row.update(overrides)
    return row


def active(symbol: str = "TSLA") -> dict[str, Any]:
    return {
        "symbol": symbol,
        "name": "Tesla Inc.",
        "price": 240.1,
        "changePercent": -1.2,
        "volume": 123456789,
        "dayLow": 238.05,
        "dayHigh": 245.52,
    }


def headline(title: str = "Stocks end the week mixed") -> dict[str, Any]:
    return {
        "title": title,
        "url": "https://example.com/news/market-close",
        "source": "Finnhub",
        "publishedAt": "2026-11-06T20:15:00Z",
    }


def component(name: str, score: int, weight: float) -> dict[str, Any]:
    return {"name": name, "score": score, "weight": weight}


FIVE_COMPONENTS = (
    component("volatility", 44, 0.30),
    component("trend", 58, 0.25),
    component("momentum", 50, 0.20),
    component("riskAppetite", 70, 0.15),
    component("headlineTone", 52, 0.10),
)


def inputs(**overrides: Any) -> SnapshotInputs:
    base = SnapshotInputs(
        fetched_at=datetime(2026, 11, 6, 21, 5, tzinfo=UTC),
        market_status="after_hours",
        market_status_provider="alpaca",
        indexes=SectionResult(provider="yfinance", rows=(quote(),), delay_seconds=900),
        movers=MoversResult(
            provider="alpaca",
            gainers=(mover(),),
            losers=(mover("NKE"),),
            most_active=(active(),),
        ),
        news=SectionResult(provider="finnhub", rows=(headline(),), delay_seconds=300),
        sentiment=SentimentInput(
            verdict="NEUTRAL", position=53, components=FIVE_COMPONENTS, summary="Neutral."
        ),
    )
    return replace(base, **overrides)


def test_builds_a_contract_shaped_snapshot() -> None:
    snapshot = build_snapshot(inputs())
    payload = snapshot.model_dump(mode="json")

    assert payload["schemaVersion"] == 1
    assert payload["fetchedAt"] == "2026-11-06T21:05:00Z"
    assert payload["sentiment"]["marketStatus"] == "after_hours"
    assert payload["feedDelaySeconds"] == 900
    assert payload["sources"] == {
        "indexes": "yfinance",
        "movers": "alpaca",
        "news": "finnhub",
        "status": "alpaca",
    }
    assert payload["status"] == {
        "indexes": "fresh",
        "movers": "fresh",
        "news": "fresh",
        "sentiment": "fresh",
    }
    assert payload["errors"] == []
    # Round-trip through the generated model: the builder output is schema-shaped.
    assert MarketSnapshot.model_validate(payload) == snapshot


def test_invalid_rows_are_dropped_and_recorded() -> None:
    snapshot = build_snapshot(
        inputs(
            indexes=SectionResult(
                provider="yfinance",
                rows=(quote(), quote(price=0), quote(symbol="")),
                delay_seconds=900,
            ),
            movers=MoversResult(
                provider="alpaca",
                gainers=(mover(), mover("BAD", changePercent=5000)),
                losers=(),
                most_active=(),
            ),
        )
    )

    assert [card.symbol for card in snapshot.indexes] == ["^GSPC"]
    assert [row.symbol for row in snapshot.gainers] == ["NVDA"]
    sections = [error.section for error in snapshot.errors]
    assert sections == ["indexes", "indexes", "movers"]
    # Messages name the field and reason but never echo the payload (AGENTS.md rule 2).
    for error in snapshot.errors:
        assert error.provider in {"yfinance", "alpaca"}
        assert "7475.46" not in error.message
        assert "BAD" not in error.message
        assert len(error.message) < 100


def test_proxy_etf_and_sparkline_survive_the_build() -> None:
    snapshot = build_snapshot(
        inputs(
            indexes=SectionResult(
                provider="alpaca",
                rows=(quote(symbol="SPY", isProxy=True, sparkline=[1.0, 2.0, 3.0]),),
            )
        )
    )

    card = snapshot.indexes[0]
    assert card.is_proxy is True
    assert card.sparkline == [1.0, 2.0, 3.0]


def test_fewer_than_three_components_forces_unknown() -> None:
    snapshot = build_snapshot(
        inputs(
            sentiment=SentimentInput(
                verdict="BULLISH",
                position=70,
                components=FIVE_COMPONENTS[:2],
            )
        )
    )

    # Schema allOf rule: 1-2 components cannot carry a direction (docs/sentiment.md §4).
    assert snapshot.sentiment.verdict == "UNKNOWN"
    assert snapshot.sentiment.position == 70
    assert snapshot.sentiment.components is not None
    assert len(snapshot.sentiment.components) == 2


def test_three_components_keep_their_verdict() -> None:
    snapshot = build_snapshot(
        inputs(
            sentiment=SentimentInput(verdict="BULLISH", position=61, components=FIVE_COMPONENTS[:3])
        )
    )

    assert snapshot.sentiment.verdict == "BULLISH"


def test_missing_sentiment_falls_back_to_unknown_and_neutral() -> None:
    snapshot = build_snapshot(inputs(sentiment=None))

    assert snapshot.sentiment.verdict == "UNKNOWN"
    assert snapshot.sentiment.position == 50
    assert snapshot.sentiment.components == []
    # Headlines come from the news section, so they survive a missing mood (FR-11).
    assert len(snapshot.sentiment.headlines) == 1
    assert snapshot.status["sentiment"] == "error"


def test_failed_index_section_keeps_the_last_good_set() -> None:
    previous = build_snapshot(inputs())

    snapshot = build_snapshot(
        inputs(
            indexes=SectionResult(provider="yfinance", rows=(quote(price=-1),)),
            previous=previous,
        )
    )

    assert [card.symbol for card in snapshot.indexes] == ["^GSPC"]
    assert snapshot.status["indexes"] == "stale"
    assert any(error.section == "indexes" for error in snapshot.errors)


def test_failed_movers_section_keeps_the_last_good_lists() -> None:
    previous = build_snapshot(inputs())

    snapshot = build_snapshot(
        inputs(
            movers=MoversResult(provider="alpaca", gainers=(mover(price=0),)),
            previous=previous,
        )
    )

    assert [row.symbol for row in snapshot.gainers] == ["NVDA"]
    assert snapshot.status["movers"] == "stale"


def test_empty_movers_without_history_is_an_error_not_a_crash() -> None:
    snapshot = build_snapshot(inputs(movers=MoversResult(provider="alpaca")))

    assert snapshot.gainers == []
    assert snapshot.losers == []
    assert snapshot.most_active == []
    assert snapshot.status["movers"] == "error"


def test_no_index_data_and_no_history_raises() -> None:
    with pytest.raises(SnapshotUnavailable):
        build_snapshot(inputs(indexes=SectionResult(provider="yfinance")))


def test_movers_and_headlines_are_capped_by_the_schema() -> None:
    twelve = tuple(mover(f"S{i}") for i in range(12))
    seven_headlines = tuple(headline(f"h{i}") for i in range(7))
    snapshot = build_snapshot(
        inputs(
            movers=MoversResult(provider="alpaca", gainers=twelve),
            news=SectionResult(provider="finnhub", rows=seven_headlines),
        )
    )

    assert len(snapshot.gainers) == 10
    assert len(snapshot.sentiment.headlines) == 5


def test_feed_delay_is_the_slowest_contributing_feed() -> None:
    snapshot = build_snapshot(
        inputs(news=SectionResult(provider="finnhub", rows=(headline(),), delay_seconds=1800))
    )

    assert snapshot.feed_delay_seconds == 1800


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_snapshot(inputs(fetched_at=datetime(2026, 11, 6, 21, 5)))


def test_building_twice_from_the_same_inputs_is_deterministic() -> None:
    assert build_snapshot(inputs()) == build_snapshot(inputs())
