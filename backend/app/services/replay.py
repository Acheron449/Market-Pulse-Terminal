"""Replay mode: build a snapshot from a recorded provider payload, with no network access.

Providers are not wired yet, so this is what ``GET /api/market`` can honestly serve until
the registry lands. A replayed snapshot is never presented as live: every section is
marked ``stale`` and an ``errors[]`` entry names the recording it came from, which satisfies
the "explicitly flagged as a demo" exemption in AGENTS.md rule 9. Production never replays.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT, Settings
from app.models import MarketSnapshot, MarketStatus, SectionStatus, SnapshotError
from app.services.snapshot_builder import (
    MoversResult,
    SectionResult,
    SentimentInput,
    SnapshotInputs,
    SnapshotUnavailable,
    build_snapshot,
)

logger = logging.getLogger(__name__)

#: Recorded provider payload used by replay mode. Shape fixtures, not a live capture.
RECORDING_PATH = REPO_ROOT / "backend" / "fixtures" / "provider-recording.json"

DISCLOSURE_SECTION = "snapshot"


def load_replay_snapshot(settings: Settings, *, path: Path | None = None) -> MarketSnapshot | None:
    """Build the replay snapshot, or return ``None`` when replay is not allowed or usable.

    Boot must never fail because a development fixture is missing or corrupt: the route
    answers 503 instead, which is the same state a cold start with no providers reaches.
    """
    if settings.app_env == "production":
        return None

    recording_path = path or RECORDING_PATH
    if not recording_path.is_file():
        logger.warning("replay recording not found at %s", recording_path)
        return None

    try:
        recording = json.loads(recording_path.read_text(encoding="utf-8"))
        return build_from_recording(recording)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("replay recording at %s is unreadable: %s", recording_path, exc)
        return None
    except (KeyError, TypeError, ValueError, SnapshotUnavailable) as exc:
        logger.warning("replay recording at %s does not fit the contract: %s", recording_path, exc)
        return None


def build_from_recording(recording: Mapping[str, Any]) -> MarketSnapshot:
    """Map a recorded provider payload onto builder inputs and flag the result as replay."""
    captured_at: str = recording["capturedAt"]
    sections: Mapping[str, Any] = recording["sections"]

    quotes = sections["quotes"]
    movers = sections["movers"]
    news = sections["news"]
    market_status = sections["marketStatus"]
    sentiment = recording["sentiment"]

    snapshot = build_snapshot(
        SnapshotInputs(
            fetched_at=datetime.fromisoformat(captured_at.replace("Z", "+00:00")),
            market_status=_market_status(market_status["value"]),
            market_status_provider=market_status["source"],
            indexes=SectionResult(
                provider=quotes["source"],
                rows=tuple(quotes["rows"]),
                delay_seconds=int(quotes.get("delaySeconds", 0)),
            ),
            movers=MoversResult(
                provider=movers["source"],
                gainers=tuple(movers["gainers"]),
                losers=tuple(movers["losers"]),
                most_active=tuple(movers["mostActive"]),
                delay_seconds=int(movers.get("delaySeconds", 0)),
            ),
            news=SectionResult(
                provider=news["source"],
                rows=tuple(news["rows"]),
                delay_seconds=int(news.get("delaySeconds", 0)),
            ),
            sentiment=SentimentInput(
                verdict=sentiment["verdict"],
                position=int(sentiment["position"]),
                components=tuple(sentiment.get("components", ())),
                summary=str(sentiment.get("summary", "")),
            ),
        )
    )
    return _mark_as_replay(snapshot, captured_at)


def _mark_as_replay(snapshot: MarketSnapshot, captured_at: str) -> MarketSnapshot:
    """Downgrade every section to stale and disclose the recording (rule 9)."""
    stale: dict[str, SectionStatus] = {name: "stale" for name in snapshot.status}
    disclosure = SnapshotError(
        section=DISCLOSURE_SECTION,
        provider="replay",
        message=(
            f"replaying recorded provider data captured at {captured_at}; "
            "no live provider is configured"
        ),
    )
    return snapshot.model_copy(
        update={"status": stale, "errors": [*snapshot.errors, disclosure]},
    )


def _market_status(value: str) -> MarketStatus:
    """Narrow the recording's string to the contract enum, failing loudly if it is wrong."""
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
    raise ValueError(f"unknown marketStatus {value!r}")
