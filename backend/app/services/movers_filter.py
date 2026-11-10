"""Movers filters (FR-7): configurable price, volume and instrument exclusions.

The reference build's screener surfaces penny stocks and 3x leveraged ETFs, which makes
the most-active list look like noise. Filters are applied by the snapshot service before
the builder validates rows, and every threshold comes from configuration.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

Row = Mapping[str, Any]

#: Suffixes used by warrants, rights and units, e.g. ``ABCDW``, ``ABCD.RT``, ``ABCDU``.
WARRANT_PATTERN = re.compile(r"^(?P<base>[A-Z]{1,4})(?:\.?(?:WS|WT|W|RT|R|U))$")

#: Names that identify a leveraged or inverse product. Matched case-insensitively.
LEVERAGED_TOKENS = (
    "2X",
    "3X",
    "4X",
    "BULL",
    "BEAR",
    "ULTRA",
    "LEVERAGED",
    "INVERSE",
    "DIREXION DAILY",
    "PROSHARES ULTRA",
)

#: Symbols that are leveraged even when the vendor name is unhelpful.
LEVERAGED_SYMBOLS = frozenset(
    {
        "TQQQ",
        "SQQQ",
        "SPXL",
        "SPXS",
        "SOXL",
        "SOXS",
        "TNA",
        "TZA",
        "UPRO",
        "SDOW",
        "UDOW",
        "LABU",
        "LABD",
        "FNGU",
        "FNGD",
        "YINN",
        "YANG",
        "NUGT",
        "DUST",
        "JNUG",
        "JDST",
    }
)


@dataclass(frozen=True, slots=True)
class MoverFilters:
    """Thresholds from configuration (SRS Appendix A)."""

    min_price: float = 1.0
    min_volume: float = 100_000
    exclude_warrants: bool = True
    exclude_leveraged_etfs: bool = True


@dataclass(frozen=True, slots=True)
class FilteredMovers:
    gainers: tuple[Row, ...]
    losers: tuple[Row, ...]
    most_active: tuple[Row, ...]
    dropped: int = 0


def is_warrant_or_right(symbol: str) -> bool:
    return bool(WARRANT_PATTERN.match(symbol.upper()))


def is_leveraged(symbol: str, name: str = "") -> bool:
    if symbol.upper() in LEVERAGED_SYMBOLS:
        return True
    haystack = name.upper()
    return any(token in haystack for token in LEVERAGED_TOKENS)


def _keep(row: Row, filters: MoverFilters, *, check_volume: bool) -> bool:
    symbol = str(row.get("symbol", ""))
    name = str(row.get("name", ""))
    price = row.get("price")
    if not symbol or not isinstance(price, (int, float)) or price < filters.min_price:
        return False
    if filters.exclude_warrants and is_warrant_or_right(symbol):
        return False
    if filters.exclude_leveraged_etfs and is_leveraged(symbol, name):
        return False
    if check_volume:
        volume = row.get("volume")
        if not isinstance(volume, (int, float)) or volume < filters.min_volume:
            return False
    return True


def apply_filters(
    *,
    gainers: Sequence[Row],
    losers: Sequence[Row],
    most_active: Sequence[Row],
    filters: MoverFilters,
) -> FilteredMovers:
    """Keep rows that survive every configured rule, counting what was dropped."""
    kept_gainers = [row for row in gainers if _keep(row, filters, check_volume=False)]
    kept_losers = [row for row in losers if _keep(row, filters, check_volume=False)]
    kept_active = [row for row in most_active if _keep(row, filters, check_volume=True)]
    dropped = (
        len(gainers)
        - len(kept_gainers)
        + len(losers)
        - len(kept_losers)
        + len(most_active)
        - len(kept_active)
    )
    return FilteredMovers(
        gainers=tuple(kept_gainers),
        losers=tuple(kept_losers),
        most_active=tuple(kept_active),
        dropped=dropped,
    )


def with_overrides(filters: MoverFilters, **overrides: Any) -> MoverFilters:
    return replace(filters, **overrides)
