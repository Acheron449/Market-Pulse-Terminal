"""Provider contract (FR-1): one interface, declared capabilities, normalised rows.

Providers return *contract-shaped* rows keyed by the snapshot's camelCase field names, so
the snapshot builder is the single validation gate (`AGENTS.md` rule 6) and no second
model layer has to be kept in sync with the schema. Nothing outside the registry may call
a provider (`AGENTS.md` rule 3).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

Capability = Literal["quotes", "movers", "status", "news", "history"]
Row = dict[str, Any]


class ProviderError(RuntimeError):
    """A provider failed in a way that should trigger failover.

    Messages are built from constants and HTTP status codes only: response bodies can
    contain account identifiers, so they never reach a log line (`AGENTS.md` rule 2).
    """

    def __init__(self, provider: str, capability: str, reason: str) -> None:
        super().__init__(f"{provider}.{capability}: {reason}")
        self.provider = provider
        self.capability = capability
        self.reason = reason


@dataclass(frozen=True, slots=True)
class MoversPayload:
    """The three mover lists from one screener call, sharing provenance."""

    gainers: tuple[Row, ...] = ()
    losers: tuple[Row, ...] = ()
    most_active: tuple[Row, ...] = ()

    def is_empty(self) -> bool:
        return not (self.gainers or self.losers or self.most_active)


@dataclass(frozen=True, slots=True)
class Bar:
    """One OHLCV bar. ``time`` is epoch milliseconds UTC (docs/tradingview.md §3)."""

    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "time": self.time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


class MarketDataProvider:
    """What every adapter offers. Unsupported capabilities are never called.

    The defaults fail loudly: declaring a capability in ``capabilities`` without
    implementing the matching method is a bug, and the registry will fail over from it.
    """

    name: str = ""
    capabilities: frozenset[Capability] = frozenset()

    def is_configured(self) -> bool:
        """False when the adapter has no credentials, so the registry can skip it."""
        return True

    def _unsupported(self, capability: str) -> ProviderError:
        return ProviderError(self.name, capability, "capability not supported")

    async def quotes(self, symbols: Sequence[str]) -> list[Row]:
        """Index/ETF quote rows: symbol, label, price, change, changePercent, sparkline."""
        raise self._unsupported("quotes")

    async def movers(self) -> MoversPayload:
        """Gainers, losers and most-active rows from one screener call."""
        raise self._unsupported("movers")

    async def market_status(self) -> str:
        """One of the contract's marketStatus values."""
        raise self._unsupported("status")

    async def news(self, limit: int) -> list[Row]:
        """Headline rows: title, url, source, publishedAt (UTC ISO-8601)."""
        raise self._unsupported("news")

    async def daily_closes(self, symbol: str, days: int) -> list[float]:
        """Daily closing prices, oldest first, for the sentiment history inputs."""
        raise self._unsupported("history")

    async def bars(self, symbol: str, resolution: str, start_ms: int, end_ms: int) -> list[Bar]:
        """OHLCV bars for the chart drill-down, ascending by time."""
        raise self._unsupported("history")


def provider_names(providers: Sequence[MarketDataProvider]) -> list[str]:
    return [provider.name for provider in providers]
