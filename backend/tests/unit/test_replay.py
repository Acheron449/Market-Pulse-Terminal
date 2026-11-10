"""Replay mode: never in production, always disclosed, never fatal on a bad fixture."""

import json
from pathlib import Path

from app.core.config import Settings
from app.models import MarketSnapshot
from app.services.replay import RECORDING_PATH, build_from_recording, load_replay_snapshot


def dev_settings() -> Settings:
    return Settings(_env_file=None, app_env="development")


def test_production_never_replays_a_recording() -> None:
    settings = Settings(_env_file=None, app_env="production")

    assert load_replay_snapshot(settings) is None


def test_missing_recording_returns_none(tmp_path: Path) -> None:
    assert load_replay_snapshot(dev_settings(), path=tmp_path / "absent.json") is None


def test_unreadable_recording_returns_none(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    assert load_replay_snapshot(dev_settings(), path=broken) is None


def test_recording_with_a_wrong_market_status_returns_none(tmp_path: Path) -> None:
    recording = json.loads(RECORDING_PATH.read_text(encoding="utf-8"))
    recording["sections"]["marketStatus"]["value"] = "lunch_break"
    path = tmp_path / "recording.json"
    path.write_text(json.dumps(recording), encoding="utf-8")

    assert load_replay_snapshot(dev_settings(), path=path) is None


def test_replay_snapshot_is_stale_and_disclosed() -> None:
    snapshot = load_replay_snapshot(dev_settings())

    assert snapshot is not None
    assert snapshot.schema_version == 1
    assert snapshot.fetched_at == "2026-11-06T21:05:00Z"
    assert len(snapshot.indexes) == 5
    assert all(status == "stale" for status in snapshot.status.values())
    disclosure = [error for error in snapshot.errors if error.section == "snapshot"]
    assert len(disclosure) == 1
    assert disclosure[0].provider == "replay"
    assert "2026-11-06T21:05:00Z" in disclosure[0].message


def test_replay_recording_satisfies_the_contract() -> None:
    payload = json.loads(RECORDING_PATH.read_text(encoding="utf-8"))

    snapshot = build_from_recording(payload)

    assert isinstance(snapshot, MarketSnapshot)
    components = snapshot.sentiment.components or []
    assert len(components) == 5
    assert abs(sum(component.weight for component in components) - 1.0) < 1e-9
    assert snapshot.sentiment.verdict == "NEUTRAL"
    assert snapshot.feed_delay_seconds == 900
