"""Process-wide last-good snapshot (FR-9, FR-18).

The scheduler will replace it after each build; routes read it and never block on a
provider. A single attribute swap is atomic under the event loop, so readers cannot see a
half-built snapshot.
"""

from __future__ import annotations

from app.models import MarketSnapshot


class SnapshotStore:
    """Holds the most recent snapshot, or nothing before the first successful build."""

    def __init__(self) -> None:
        self._snapshot: MarketSnapshot | None = None

    def current(self) -> MarketSnapshot | None:
        return self._snapshot

    def replace(self, snapshot: MarketSnapshot) -> None:
        self._snapshot = snapshot

    def clear(self) -> None:
        self._snapshot = None
