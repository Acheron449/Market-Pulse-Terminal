"""Sentiment engine cases from docs/sentiment.md §5 and §10."""

import math

import pytest

from app.services.sentiment import (
    MoodInputs,
    compute_mood,
    distance_from_average,
    headline_tone,
    percentile_of_last,
    round_half_up,
    verdict_for,
)


def five_index_changes(spx: float, ixic: float, dji: float, rut: float) -> dict[str, float]:
    return {"^GSPC": spx, "^IXIC": ixic, "^DJI": dji, "^RUT": rut}


def example_a() -> MoodInputs:
    return MoodInputs(
        market_status="regular",
        index_changes=five_index_changes(0.45, 0.62, 0.31, 0.28),
        vix_percentile=40.0,
        vix_change_percent=2.0,
        spx_distance_from_sma_percent=1.2,
        # One clearly bullish headline and nine neutral ones: mean tone +0.10, score 55.
        headlines=[{"title": "Stocks gain on strong earnings"}]
        + [{"title": "Markets await the Fed"}] * 9,
    )


def example_b() -> MoodInputs:
    return MoodInputs(
        market_status="regular",
        index_changes=five_index_changes(-1.10, -1.45, -0.95, -1.30),
        vix_percentile=85.0,
        vix_change_percent=6.0,
        spx_distance_from_sma_percent=-2.1,
    )


def test_example_a_is_neutral_at_54() -> None:
    mood = compute_mood(example_a())

    assert mood.position == 54
    assert mood.verdict == "NEUTRAL"
    assert [component.name for component in mood.components] == [
        "volatility",
        "trend",
        "momentum",
        "riskAppetite",
        "headlineTone",
    ]
    assert math.isclose(sum(component.weight for component in mood.components), 1.0)


def test_example_b_is_bearish_at_24_with_renormalised_weights() -> None:
    mood = compute_mood(example_b(), headline_tone_enabled=False)

    assert mood.position == 24
    assert mood.verdict == "BEARISH"
    assert len(mood.components) == 4
    assert math.isclose(sum(component.weight for component in mood.components), 1.0)
    assert math.isclose(mood.components[0].weight, 0.30 / 0.90, rel_tol=1e-9)


def test_example_c_two_components_is_unknown_at_54() -> None:
    # volatility 40 (percentile 60 inverted, +1% VIX) and trend 70 (+2% over the 50-day).
    mood = compute_mood(
        MoodInputs(vix_percentile=60.0, vix_change_percent=1.0, spx_distance_from_sma_percent=2.0)
    )

    assert mood.position == 54
    assert mood.verdict == "UNKNOWN"
    assert len(mood.components) == 2


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        (0, "BEARISH"),
        (25, "BEARISH"),
        (26, "UNCERTAIN"),
        (44, "UNCERTAIN"),
        (45, "NEUTRAL"),
        (60, "NEUTRAL"),
        (61, "BULLISH"),
        (100, "BULLISH"),
    ],
)
def test_band_boundaries(position: int, expected: str) -> None:
    assert verdict_for(position) == expected


def test_rising_vix_lowers_the_score() -> None:
    quiet = compute_mood(MoodInputs(vix_percentile=50.0, vix_change_percent=-5.0))
    nervous = compute_mood(MoodInputs(vix_percentile=50.0, vix_change_percent=+5.0))

    assert quiet.position > nervous.position


def test_saturation_clamps_components() -> None:
    mood = compute_mood(
        MoodInputs(
            index_changes=five_index_changes(9.0, 9.0, 9.0, 9.0),
            spx_distance_from_sma_percent=9.0,
        )
    )

    for component in mood.components:
        assert 0 <= component.score <= 100
    assert mood.verdict == "BULLISH"
    # trend and momentum saturate at 100; risk appetite stays neutral at 50, so the
    # renormalised score over those three weights is 87.5 -> 88.
    assert mood.position == 88


def test_all_inputs_missing_is_unknown_at_50() -> None:
    mood = compute_mood(MoodInputs())

    assert mood.verdict == "UNKNOWN"
    assert mood.position == 50
    assert mood.components == ()


def test_non_finite_input_is_treated_as_missing() -> None:
    mood = compute_mood(
        MoodInputs(
            vix_percentile=float("nan"),
            vix_change_percent=float("inf"),
            spx_distance_from_sma_percent=float("nan"),
            index_changes={"^GSPC": float("inf")},
        )
    )

    assert mood.available == 0
    assert mood.verdict == "UNKNOWN"


def test_momentum_needs_all_four_equity_indices() -> None:
    mood = compute_mood(MoodInputs(index_changes={"^GSPC": 1.0, "^IXIC": 1.0}))

    assert all(component.name != "momentum" for component in mood.components)


def test_round_half_up_matches_the_contract() -> None:
    assert round_half_up(54.44) == 54
    assert round_half_up(54.5) == 55
    assert round_half_up(24.5) == 25


def test_headline_tone_lexicon() -> None:
    assert headline_tone([{"title": "Stocks surge on strong earnings"}]) == 1.0
    assert headline_tone([{"title": "Stocks plunge as recession fear grows"}]) == -1.0
    assert headline_tone([{"title": "Markets await the Fed"}]) == 0.0
    assert headline_tone([]) is None


def test_history_helpers() -> None:
    closes = [100.0] * 49 + [110.0]
    assert distance_from_average(closes, 50) is not None
    assert distance_from_average([100.0], 50) is None
    assert percentile_of_last([1.0, 2.0, 3.0]) == pytest.approx(83.3333, rel=1e-3)
    assert percentile_of_last([]) is None
