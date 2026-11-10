"""yfinance adapter: index levels, sparklines, screeners and chart bars (SRS §4.1).

Index levels are not on the free Alpaca or Finnhub equity feeds, so this is the only
source for ``^GSPC``, ``^IXIC``, ``^DJI``, ``^RUT`` and ``^VIX``. yfinance is synchronous
and unofficial, so every call runs in a worker thread and every failure becomes a
``ProviderError`` the registry can fail over from (`AGENTS.md` rule 3).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.providers.base import (
    Bar,
    Capability,
    MarketDataProvider,
    MoversPayload,
    ProviderError,
    Row,
)

logger = logging.getLogger(__name__)

#: Display label and colour-inversion flag per index (FR-19, FR-21).
SYMBOL_META: dict[str, tuple[str, bool]] = {
    "^GSPC": ("S&P 500", False),
    "^IXIC": ("NASDAQ", False),
    "^DJI": ("DOW JONES", False),
    "^RUT": ("RUSSELL 2000", False),
    "^VIX": ("VIX", True),
}

#: Chart resolution -> Yahoo interval.
RESOLUTION_TO_INTERVAL = {"1": "1m", "5": "5m", "15": "15m", "60": "60m", "1D": "1d"}

SCREENER_BY_LIST = {"gainers": "day_gainers", "losers": "day_losers", "most_active": "most_actives"}


def _yf() -> Any:
    try:
        import yfinance
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ProviderError("yfinance", "quotes", "yfinance is not installed") from exc
    return yfinance


def _downsample(values: list[float], limit: int) -> list[float]:
    if limit <= 0 or len(values) <= limit:
        return values
    step = len(values) / limit
    return [values[min(len(values) - 1, int(index * step))] for index in range(limit)]


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class YFinanceProvider(MarketDataProvider):
    """Unofficial Yahoo wrapper: the sole index source and the movers fallback."""

    name = "yfinance"
    capabilities: frozenset[Capability] = frozenset({"quotes", "movers", "history"})

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def is_configured(self) -> bool:
        # No key exists: the operator opts in, so tests and replay never touch the network.
        return self._settings.enable_live_data

    # -- quotes ----------------------------------------------------------------
    async def quotes(self, symbols: Sequence[str]) -> list[Row]:
        return await asyncio.to_thread(self._quotes_sync, list(symbols))

    def _quotes_sync(self, symbols: list[str]) -> list[Row]:
        yf = _yf()
        try:
            frame = yf.download(
                tickers=" ".join(symbols),
                period="1d",
                interval="5m",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
        except Exception as exc:  # noqa: BLE001 - vendor libraries raise anything
            raise ProviderError(self.name, "quotes", type(exc).__name__) from exc
        if frame is None or getattr(frame, "empty", True):
            raise ProviderError(self.name, "quotes", "empty payload")

        rows: list[Row] = []
        for symbol in symbols:
            try:
                closes = frame[symbol]["Close"].dropna()
                opens = frame[symbol]["Open"].dropna()
            except (KeyError, TypeError):
                continue
            if closes.empty or opens.empty:
                continue
            price = float(closes.iloc[-1])
            reference = float(opens.iloc[0])
            if reference <= 0 or price <= 0:
                continue
            change = price - reference
            label, invert = SYMBOL_META.get(symbol, (symbol.lstrip("^"), False))
            rows.append(
                {
                    "symbol": symbol,
                    "label": label,
                    "price": round(price, 4),
                    "change": round(change, 4),
                    "changePercent": round(change / reference * 100, 4),
                    "invert": invert,
                    "sparkline": [
                        round(value, 4)
                        for value in _downsample(
                            [float(value) for value in closes.tolist()],
                            self._settings.sparkline_points,
                        )
                    ],
                    "isProxy": False,
                    "asOf": _iso(datetime.now(UTC)),
                }
            )
        if not rows:
            raise ProviderError(self.name, "quotes", "no usable quotes")
        return rows

    # -- movers ----------------------------------------------------------------
    async def movers(self) -> MoversPayload:
        return await asyncio.to_thread(self._movers_sync)

    def _movers_sync(self) -> MoversPayload:
        yf = _yf()
        try:
            gainers = self._screen(yf, "gainers")
            losers = self._screen(yf, "losers")
            active = self._screen(yf, "most_active", with_range=True)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(self.name, "movers", type(exc).__name__) from exc
        return MoversPayload(
            gainers=tuple(gainers), losers=tuple(losers), most_active=tuple(active)
        )

    def _screen(self, yf: Any, key: str, *, with_range: bool = False) -> list[Row]:
        result = yf.screen(SCREENER_BY_LIST[key], count=25)
        quotes = list(result.get("quotes", [])) if isinstance(result, dict) else []
        rows: list[Row] = []
        for item in quotes:
            symbol = str(item.get("symbol", ""))
            price = item.get("regularMarketPrice")
            percent = item.get("regularMarketChangePercent")
            if (
                not symbol
                or not isinstance(price, (int, float))
                or not isinstance(percent, (int, float))
            ):
                continue
            row: Row = {
                "symbol": symbol,
                "name": str(item.get("shortName") or item.get("longName") or symbol),
                "price": float(price),
                "changePercent": float(percent),
            }
            if with_range:
                row["volume"] = float(item.get("regularMarketVolume") or 0)
                low = item.get("regularMarketDayLow")
                high = item.get("regularMarketDayHigh")
                if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
                    continue
                row["dayLow"] = float(low)
                row["dayHigh"] = float(high)
            rows.append(row)
        if not rows:
            raise ProviderError(self.name, "movers", f"{key} screener returned nothing")
        return rows

    # -- history ---------------------------------------------------------------
    async def daily_closes(self, symbol: str, days: int) -> list[float]:
        return await asyncio.to_thread(self._daily_closes_sync, symbol, days)

    def _daily_closes_sync(self, symbol: str, days: int) -> list[float]:
        yf = _yf()
        try:
            frame = yf.Ticker(symbol).history(
                period=f"{max(days, 60) + 40}d", interval="1d", auto_adjust=False
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(self.name, "history", type(exc).__name__) from exc
        if frame is None or getattr(frame, "empty", True):
            raise ProviderError(self.name, "history", "empty payload")
        closes = [float(value) for value in frame["Close"].dropna().tolist()]
        if not closes:
            raise ProviderError(self.name, "history", "no closes")
        return closes[-days:]

    async def bars(self, symbol: str, resolution: str, start_ms: int, end_ms: int) -> list[Bar]:
        return await asyncio.to_thread(self._bars_sync, symbol, resolution, start_ms, end_ms)

    def _bars_sync(self, symbol: str, resolution: str, start_ms: int, end_ms: int) -> list[Bar]:
        interval = RESOLUTION_TO_INTERVAL.get(resolution)
        if interval is None:
            raise ProviderError(self.name, "history", "unsupported resolution")
        yf = _yf()
        start = datetime.fromtimestamp(start_ms / 1000, tz=UTC)
        end = datetime.fromtimestamp(end_ms / 1000, tz=UTC)
        # yfinance caps intraday history; ask for a little more than the visible range.
        if interval.endswith("m") and start < datetime.now(UTC) - timedelta(days=7):
            start = datetime.now(UTC) - timedelta(days=7)
        try:
            frame = yf.Ticker(symbol).history(
                start=start, end=end, interval=interval, auto_adjust=False
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(self.name, "history", type(exc).__name__) from exc
        if frame is None or getattr(frame, "empty", True):
            raise ProviderError(self.name, "history", "empty payload")

        bars: list[Bar] = []
        for index, record in frame.iterrows():
            moment = index.to_pydatetime()
            if interval == "1d":
                # Daily bars are stamped 00:00:00 UTC, not the session open (§3 rule 2).
                stamp = int(
                    datetime(moment.year, moment.month, moment.day, tzinfo=UTC).timestamp() * 1000
                )
            else:
                stamp = int(moment.timestamp() * 1000)
            bars.append(
                Bar(
                    time=stamp,
                    open=float(record["Open"]),
                    high=float(record["High"]),
                    low=float(record["Low"]),
                    close=float(record["Close"]),
                    volume=float(record["Volume"]) if "Volume" in record else None,
                )
            )
        if not bars:
            raise ProviderError(self.name, "history", "no bars")
        return bars
