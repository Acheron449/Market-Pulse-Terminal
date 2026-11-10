"""Snapshot builder (FR-8): turn normalised provider rows into one schema-valid snapshot.

Pure functions only -- no clock reads, no I/O, no provider calls -- so a snapshot can be
rebuilt from a recording and asserted. Callers hand in *normalised* rows keyed by contract
field names; this module validates them against the generated contract models (FR-5,
AGENTS.md rule 6), keeps the last good section when a refresh fails (FR-9, AGENTS.md rule
5) and records which provider supplied each section (FR-6).

The schema-only ``allOf`` rule (fewer than three sentiment components must not produce a
directional verdict) is enforced here, because it is not expressible as a field type.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError

from app.models import (
    Component,
    Headline,
    IndexCard,
    MarketSnapshot,
    MarketStatus,
    MostActiveRow,
    Mover,
    SectionStatus,
    Sentiment,
    SnapshotError,
    Verdict,
)

#: Schema caps (``maxItems``) applied before assembly so an over-long list cannot raise.
MOVER_LIMIT = 10
HEADLINE_LIMIT = 5
COMPONENT_LIMIT = 5

#: Below this many components the verdict must be UNKNOWN (docs/sentiment.md §4).
MIN_SENTIMENT_COMPONENTS = 3


class SnapshotUnavailable(RuntimeError):
    """No usable data for a mandatory section, so no valid snapshot can be built.

    The route turns this into a 503 rather than inventing a value (AGENTS.md rule 9).
    """


@dataclass(frozen=True, slots=True)
class SectionResult:
    """One provider response for one section: normalised rows plus provenance."""

    provider: str
    rows: Sequence[Mapping[str, Any]] = ()
    #: Delay of this feed in seconds, disclosed via ``feedDelaySeconds`` (AGENTS.md §12).
    delay_seconds: int = 0


@dataclass(frozen=True, slots=True)
class MoversResult:
    """The three mover lists come from one screener call, so they share provenance."""

    provider: str
    gainers: Sequence[Mapping[str, Any]] = ()
    losers: Sequence[Mapping[str, Any]] = ()
    most_active: Sequence[Mapping[str, Any]] = ()
    delay_seconds: int = 0


@dataclass(frozen=True, slots=True)
class SentimentInput:
    """A computed mood. ``components`` are re-weighted by services/sentiment.py first."""

    verdict: Verdict
    position: int
    components: Sequence[Mapping[str, Any]] = ()
    summary: str = ""


@dataclass(frozen=True, slots=True)
class SnapshotInputs:
    """Everything one build needs. ``previous`` is the last good snapshot, if any."""

    fetched_at: datetime
    market_status: MarketStatus
    market_status_provider: str
    indexes: SectionResult
    movers: MoversResult
    news: SectionResult
    sentiment: SentimentInput | None = None
    previous: MarketSnapshot | None = None


def build_snapshot(inputs: SnapshotInputs) -> MarketSnapshot:
    """Assemble a contract-shaped snapshot, retaining last-good sections on failure."""
    errors: list[SnapshotError] = []

    indexes, indexes_status = _index_section(inputs, errors)
    gainers, losers, most_active, movers_status = _mover_sections(inputs, errors)
    headlines, news_status = _headline_section(inputs, errors)
    sentiment, sentiment_status = _sentiment_section(inputs, headlines, errors)

    return MarketSnapshot(
        schema_version=1,
        fetched_at=_timestamp(inputs.fetched_at),
        indexes=indexes,
        sentiment=sentiment,
        gainers=gainers,
        losers=losers,
        most_active=most_active,
        sources={
            "indexes": inputs.indexes.provider,
            "movers": inputs.movers.provider,
            "news": inputs.news.provider,
            "status": inputs.market_status_provider,
        },
        status={
            "indexes": indexes_status,
            "movers": movers_status,
            "news": news_status,
            "sentiment": sentiment_status,
        },
        feed_delay_seconds=_feed_delay_seconds(inputs),
        errors=errors,
    )


def _index_section(
    inputs: SnapshotInputs, errors: list[SnapshotError]
) -> tuple[list[IndexCard], SectionStatus]:
    cards = _rows(
        IndexCard,
        inputs.indexes.rows,
        section="indexes",
        provider=inputs.indexes.provider,
        errors=errors,
    )
    if cards:
        return cards, "fresh"

    previous = inputs.previous
    if previous is not None and previous.indexes:
        errors.append(
            SnapshotError(
                section="indexes",
                provider=inputs.indexes.provider,
                message="refresh produced no usable index cards; serving the last good set",
            )
        )
        return list(previous.indexes), "stale"

    # ``indexes`` is the one array the schema forbids from being empty and the header
    # cannot render without it, so there is nothing honest to serve.
    raise SnapshotUnavailable("no usable index quotes and no last-good snapshot")


def _mover_sections(
    inputs: SnapshotInputs, errors: list[SnapshotError]
) -> tuple[list[Mover], list[Mover], list[MostActiveRow], SectionStatus]:
    movers = inputs.movers
    gainers = _rows(
        Mover, movers.gainers, section="movers", provider=movers.provider, errors=errors
    )[:MOVER_LIMIT]
    losers = _rows(Mover, movers.losers, section="movers", provider=movers.provider, errors=errors)[
        :MOVER_LIMIT
    ]
    most_active = _rows(
        MostActiveRow,
        movers.most_active,
        section="movers",
        provider=movers.provider,
        errors=errors,
    )[:MOVER_LIMIT]

    if gainers or losers or most_active:
        return gainers, losers, most_active, "fresh"

    previous = inputs.previous
    if previous is not None and (previous.gainers or previous.losers or previous.most_active):
        errors.append(
            SnapshotError(
                section="movers",
                provider=movers.provider,
                message="screener returned no usable rows; serving the last good lists",
            )
        )
        return list(previous.gainers), list(previous.losers), list(previous.most_active), "stale"

    # An empty mover list is valid (nothing qualified), so the snapshot still builds.
    return [], [], [], "error"


def _headline_section(
    inputs: SnapshotInputs, errors: list[SnapshotError]
) -> tuple[list[Headline], SectionStatus]:
    headlines = _rows(
        Headline,
        inputs.news.rows,
        section="news",
        provider=inputs.news.provider,
        errors=errors,
    )[:HEADLINE_LIMIT]
    if headlines:
        return headlines, "fresh"

    previous = inputs.previous
    if previous is not None and previous.sentiment.headlines:
        errors.append(
            SnapshotError(
                section="news",
                provider=inputs.news.provider,
                message="no usable headlines; serving the last good list",
            )
        )
        return list(previous.sentiment.headlines), "stale"

    return [], "error"


def _sentiment_section(
    inputs: SnapshotInputs, headlines: list[Headline], errors: list[SnapshotError]
) -> tuple[Sentiment, SectionStatus]:
    if inputs.sentiment is None:
        return _unknown_sentiment(inputs, headlines), "error"

    source = inputs.sentiment
    components = _rows(
        Component,
        source.components,
        section="sentiment",
        provider=None,
        errors=errors,
    )[:COMPONENT_LIMIT]

    # Schema ``allOf`` rule: 1-2 components cannot carry a direction, so the verdict is
    # UNKNOWN and the UI shows no needle colour (docs/sentiment.md §4).
    verdict: Verdict = source.verdict if len(components) >= MIN_SENTIMENT_COMPONENTS else "UNKNOWN"

    candidate = _rows(
        Sentiment,
        [
            {
                "verdict": verdict,
                "position": source.position,
                "marketStatus": inputs.market_status,
                "summary": source.summary,
                "headlines": [headline.model_dump() for headline in headlines],
                "components": [component.model_dump() for component in components],
            }
        ],
        section="sentiment",
        provider=None,
        errors=errors,
    )
    if not candidate:
        return _unknown_sentiment(inputs, headlines), "error"
    return candidate[0], "fresh"


def _unknown_sentiment(inputs: SnapshotInputs, headlines: list[Headline]) -> Sentiment:
    """No mood was computed: UNKNOWN with a neutral position (docs/sentiment.md §6)."""
    return Sentiment(
        verdict="UNKNOWN",
        position=50,
        market_status=inputs.market_status,
        summary="",
        headlines=headlines,
        components=[],
    )


def _rows[ModelT: BaseModel](
    model: type[ModelT],
    rows: Iterable[Mapping[str, Any]],
    *,
    section: str,
    provider: str | None,
    errors: list[SnapshotError],
) -> list[ModelT]:
    """Validate rows against the contract model, dropping (and recording) bad ones."""
    validated: list[ModelT] = []
    for row in rows:
        try:
            validated.append(model.model_validate(row))
        except ValidationError as exc:
            # Only the field and the reason: the row itself never reaches the message,
            # so keys, account identifiers and raw payloads stay out (AGENTS.md rule 2).
            errors.append(
                SnapshotError(
                    section=section,
                    provider=provider,
                    message=f"dropped invalid row ({_first_problem(exc)})",
                )
            )
    return validated


def _first_problem(exc: ValidationError) -> str:
    first = exc.errors()[0]
    location = ".".join(str(part) for part in first["loc"]) or "row"
    return f"{location}: {first['msg']}"


def _feed_delay_seconds(inputs: SnapshotInputs) -> int:
    """The slowest contributing feed decides the disclosed delay (AGENTS.md §12)."""
    return max(
        inputs.indexes.delay_seconds,
        inputs.movers.delay_seconds,
        inputs.news.delay_seconds,
    )


def _timestamp(value: datetime) -> str:
    """UTC ISO-8601 with a Z suffix, which the contract's pattern requires (FR-8)."""
    if value.tzinfo is None:
        raise ValueError("fetched_at must be timezone-aware; the contract is UTC")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
