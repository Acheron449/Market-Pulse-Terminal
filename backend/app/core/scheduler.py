"""Auto-update scheduler (FR-13, SRS §9).

Adds jitter, skips a cycle if the previous one is still running (the service lock enforces
that), and backs off exponentially after failures. The cadence comes from the market state
so a closed market costs almost nothing.
"""

from __future__ import annotations

import asyncio
import logging
import random

from app.core.config import Settings
from app.models import MarketStatus
from app.services.market_hours import cadences_for
from app.services.snapshot_service import SnapshotService

logger = logging.getLogger(__name__)


class SnapshotScheduler:
    """A single background loop; one process owns the refresh cycle."""

    def __init__(self, service: SnapshotService, settings: Settings) -> None:
        self._service = service
        self._settings = settings
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._failures = 0

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopped.clear()
            self._task = asyncio.create_task(self._run(), name="snapshot-scheduler")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown path
                pass
            self._task = None

    @property
    def failures(self) -> int:
        return self._failures

    def _next_delay(self) -> float:
        status: MarketStatus = self._service.market_status()
        cadence = cadences_for(self._settings, status)
        base = max(5, min(cadence["quotes"], cadence["movers"], cadence["status"]))
        jitter = self._settings.scheduler_jitter_fraction
        return base * random.uniform(1 - jitter, 1 + jitter)

    async def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                await self._service.refresh()
                self._failures = 0
                delay = self._next_delay()
            except asyncio.CancelledError:  # pragma: no cover - shutdown
                raise
            except Exception as exc:  # noqa: BLE001 - the loop must survive every error
                self._failures += 1
                delay = min(
                    self._settings.scheduler_max_backoff_seconds,
                    max(5, 5 * 2 ** (self._failures - 1)),
                )
                logger.warning(
                    "refresh cycle failed (%s: %s); retrying in %.0fs",
                    type(exc).__name__,
                    str(exc)[:160],
                    delay,
                )
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=delay)
            except TimeoutError:
                continue
