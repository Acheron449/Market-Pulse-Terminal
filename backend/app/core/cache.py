"""SQLite persistence for the last-good snapshot (SRS §3, FR-18).

The snapshot is stored as JSON exactly as it goes on the wire, so a cold start serves the
previous build immediately and the UI never flashes an empty dashboard. Writes are atomic
(temporary file inside SQLite's own transaction) and run off the event loop.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from app.models import MarketSnapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    fetched_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT NOT NULL,
    resolution TEXT NOT NULL,
    bar_time INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (symbol, resolution, bar_time)
);
"""


class SnapshotCache:
    """Single-row last-good snapshot plus a bar cache for the chart."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._ready = False

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init_sync(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    async def init(self) -> None:
        if not self._ready:
            await asyncio.to_thread(self._init_sync)
            self._ready = True

    def _load_sync(self) -> MarketSnapshot | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM snapshots WHERE id = 1").fetchone()
        if not row:
            return None
        try:
            return MarketSnapshot.model_validate(json.loads(row[0]))
        except (ValueError, TypeError):
            # A payload written by an older contract is discarded rather than served.
            return None

    async def load(self) -> MarketSnapshot | None:
        await self.init()
        return await asyncio.to_thread(self._load_sync)

    def _save_sync(self, payload: str, fetched_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO snapshots (id, fetched_at, payload) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET fetched_at = excluded.fetched_at, "
                "payload = excluded.payload",
                (fetched_at, payload),
            )

    async def save(self, snapshot: MarketSnapshot) -> None:
        await self.init()
        payload = snapshot.model_dump_json(by_alias=True)
        await asyncio.to_thread(self._save_sync, payload, snapshot.fetched_at)
