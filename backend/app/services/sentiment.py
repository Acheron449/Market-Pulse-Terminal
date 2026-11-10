"""Market-mood engine (FR-10, SRS §10, docs/sentiment.md).

Pure functions: numbers in, numbers out, no I/O, no clock reads, no randomness. The
formulas, weights and bands are the ones written down in docs/sentiment.md, and its worked
examples A, B and C are asserted by the tests in ``tests/unit/test_sentiment.py``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.models import Component, ComponentName, MarketStatus, Verdict

EQUITY_INDICES = ("^GSPC", "^IXIC", "^DJI", "^RUT")

DEFAULT_WEIGHTS: Mapping[ComponentName, float] = {
    "volatility": 0.30,
    "trend": 0.25,
    "momentum": 0.20,
    "riskAppetite": 0.15,
    "headlineTone": 0.10,
}

DEFAULT_BANDS: Mapping[str, float] = {"bearish": 25.0, "uncertain": 44.0, "neutral": 60.0}

#: Deliberately small and explainable: no model call, no network (docs/sentiment.md §3).
BULLISH_TERMS = (
    "surge",
    "rally",
    "gain",
    "gains",
    "rise",
    "rises",
    "record high",
    "beats",
    "upgrade",
    "optimism",
    "recovery",
    "strong",
)
BEARISH_TERMS = (
    "plunge",
    "slump",
    "fall",
    "falls",
    "drop",
    "drops",
    "selloff",
    "sell-off",
    "misses",
    "downgrade",
    "fear",
    "recession",
    "weak",
)


@dataclass(frozen=True, slots=True)
class MoodInputs:
    """Everything the mood needs, all optional except the market status."""

    market_status: MarketStatus = "unknown"
    index_changes: Mapping[str, float] = field(default_factory=dict)
    vix_percentile: float | None = None
    vix_change_percent: float | None = None
    spx_distance_from_sma_percent: float | None = None
    headlines: Sequence[Mapping[str, Any]] = ()
    summary: str = ""


@dataclass(frozen=True, slots=True)
class Mood:
    verdict: Verdict
    position: int
    components: tuple[Component, ...]
    summary: str
    available: int

    @property
    def component_payload(self) -> list[dict[str, object]]:
        return [
            {"name": c.name, "score": c.score, "weight": round(c.weight, 6)}
            for c in self.components
        ]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _number(value: float | None) -> float | None:
    """Non-finite input is treated as missing, never substituted with a guess (§6)."""
    if value is None or not math.isfinite(value):
        return None
    return value


def round_half_up(value: float) -> int:
    """The contract's rounding rule: half away from zero, not banker's rounding."""
    return int(math.floor(value + 0.5)) if value >= 0 else -int(math.floor(-value + 0.5))


def headline_tone(headlines: Sequence[Mapping[str, Any]]) -> float | None:
    """Mean lexicon tone of the headlines, in -1..+1, or None when there are none."""
    if not headlines:
        return None
    scores: list[float] = []
    for headline in headlines:
        text = str(headline.get("title", "")).lower()
        bullish = sum(1 for term in BULLISH_TERMS if term in text)
        bearish = sum(1 for term in BEARISH_TERMS if term in text)
        total = bullish + bearish
        scores.append(0.0 if total == 0 else (bullish - bearish) / total)
    return sum(scores) / len(scores)


def verdict_for(position: int, bands: Mapping[str, float] | None = None) -> Verdict:
    """Band containing the integer position; bands are contiguous and inclusive."""
    thresholds = dict(bands or DEFAULT_BANDS)
    if position <= thresholds["bearish"]:
        return "BEARISH"
    if position <= thresholds["uncertain"]:
        return "UNCERTAIN"
    if position <= thresholds["neutral"]:
        return "NEUTRAL"
    return "BULLISH"


def compute_mood(
    inputs: MoodInputs,
    *,
    weights: Mapping[ComponentName, float] | None = None,
    bands: Mapping[str, float] | None = None,
    min_components: int = 3,
    headline_tone_enabled: bool = True,
) -> Mood:
    """Compute the five components, renormalise the weights and pick the verdict band."""
    effective_weights = dict(weights or DEFAULT_WEIGHTS)
    thresholds = dict(bands or DEFAULT_BANDS)
    scores: dict[ComponentName, float] = {}

    vix_percentile = _number(inputs.vix_percentile)
    vix_change = _number(inputs.vix_change_percent)
    if vix_percentile is not None and vix_change is not None:
        inverted = 100 - clamp(vix_percentile, 0, 100)
        change = 50 - clamp(vix_change * 10, -50, 50)
        scores["volatility"] = clamp(0.7 * inverted + 0.3 * change, 0, 100)

    spx_distance = _number(inputs.spx_distance_from_sma_percent)
    if spx_distance is not None:
        scores["trend"] = clamp(50 + 10 * spx_distance, 0, 100)

    changes = {
        symbol: value
        for symbol, raw in inputs.index_changes.items()
        if (value := _number(raw)) is not None
    }
    equity_changes = [changes[symbol] for symbol in EQUITY_INDICES if symbol in changes]
    if len(equity_changes) == len(EQUITY_INDICES):
        mean_change = sum(equity_changes) / len(equity_changes)
        scores["momentum"] = clamp(50 + 20 * mean_change, 0, 100)

    spx_change = changes.get("^GSPC")
    russell_change = changes.get("^RUT")
    if spx_change is not None and russell_change is not None:
        relative = russell_change - spx_change
        scores["riskAppetite"] = clamp(50 + 40 * relative, 0, 100)

    if headline_tone_enabled:
        tone = headline_tone(inputs.headlines)
        if tone is not None:
            scores["headlineTone"] = clamp(50 + 50 * tone, 0, 100)

    available = [name for name in DEFAULT_WEIGHTS if name in scores]
    if not available:
        return Mood(
            verdict="UNKNOWN", position=50, components=(), summary=inputs.summary, available=0
        )

    total_weight = sum(effective_weights[name] for name in available)
    position_float = (
        sum(effective_weights[name] * scores[name] for name in available) / total_weight
    )
    position = round_half_up(clamp(position_float, 0, 100))

    components = tuple(
        Component(
            name=name,
            score=round_half_up(scores[name]),
            weight=effective_weights[name] / total_weight,
        )
        for name in available
    )

    verdict: Verdict = (
        "UNKNOWN" if len(available) < min_components else verdict_for(position, thresholds)
    )

    return Mood(
        verdict=verdict,
        position=position,
        components=components,
        summary=inputs.summary or summarize(verdict, position, inputs, len(available)),
        available=len(available),
    )


def summarize(verdict: Verdict, position: int, inputs: MoodInputs, available: int) -> str:
    """Deterministic template (FR-12 fallback); never advice, never a prediction."""
    spx = _number(inputs.index_changes.get("^GSPC"))
    vix = _number(inputs.vix_change_percent)
    parts = [f"{verdict} mood (score {position})."]
    if spx is not None:
        parts.append(f"S&P 500 {spx:+.2f}%.")
    if vix is not None:
        parts.append(f"VIX {vix:+.2f}%.")
    parts.append(f"Based on {available} of 5 signals.")
    return " ".join(parts)


def distance_from_average(closes: Sequence[float], window: int = 50) -> float | None:
    """Percent distance of the last close from its simple moving average."""
    if len(closes) < window:
        return None
    average = sum(closes[-window:]) / window
    if average <= 0:
        return None
    return (closes[-1] - average) / average * 100.0


def percentile_of_last(closes: Sequence[float], window: int = 252) -> float | None:
    """Percentile rank of the last close within the trailing window (0-100)."""
    if len(closes) < 2:
        return None
    sample = list(closes[-window:])
    last = sample[-1]
    below = sum(1 for value in sample if value < last)
    equal = sum(1 for value in sample if value == last)
    return (below + 0.5 * equal) / len(sample) * 100.0
