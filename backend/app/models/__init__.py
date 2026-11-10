"""Snapshot contract models, generated from shared/schema/market-snapshot.schema.json.

`market_snapshot.py` is machine output: change the schema, then run
`./scripts/gen_types.sh` (AGENTS.md §5). This module is the import surface the rest of
the backend uses, so a rename in the schema surfaces here first.
"""

from app.models.market_snapshot import (
    ChangePercent,
    Component,
    ComponentName,
    Headline,
    IndexCard,
    MarketSnapshot,
    MarketStatus,
    MostActiveRow,
    Mover,
    Price,
    SectionStatus,
    SectionStatusMap,
    Sentiment,
    SnapshotError,
    SourceMap,
    TickerSymbol,
    Timestamp,
    Verdict,
)

__all__ = [
    "ChangePercent",
    "Component",
    "ComponentName",
    "Headline",
    "IndexCard",
    "MarketSnapshot",
    "MarketStatus",
    "MostActiveRow",
    "Mover",
    "Price",
    "SectionStatus",
    "SectionStatusMap",
    "Sentiment",
    "SnapshotError",
    "SourceMap",
    "TickerSymbol",
    "Timestamp",
    "Verdict",
]
