"""Static export mode (FR-17): write `market-data.json` atomically after each cycle.

Lets the dashboard run on static hosting with a scheduled job, mirroring the reference's
fallback. The write goes to a temporary file and is renamed, so a reader never sees a
half-written document.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.models import MarketSnapshot


def _write_sync(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


async def export_snapshot(path: Path, snapshot: MarketSnapshot) -> None:
    await asyncio.to_thread(_write_sync, path, snapshot.model_dump_json(by_alias=True))
