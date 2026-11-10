"""Daily provider canary: the only job allowed to call yfinance live (AGENTS.md §8).

Run it manually with the backend environment:

    cd backend && uv run python ../scripts/canary.py

It checks the one thing the whole snapshot depends on and that tests deliberately
cannot check, because they never touch the network: that Yahoo still answers for the
five index symbols with usable, recent, finite prices. A failure here is a signal to
inspect the provider, never a reason to relax the fixtures.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

SYMBOLS = ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX"]
MAX_STALENESS = timedelta(days=5)  # a long weekend plus a holiday


def main() -> int:
    try:
        import yfinance
    except ImportError:
        print("canary: yfinance is not installed (run from backend/ with uv)", file=sys.stderr)
        return 2

    frame = yfinance.download(
        tickers=" ".join(SYMBOLS),
        period="5d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    if frame is None or getattr(frame, "empty", True):
        print("canary: yfinance returned an empty frame", file=sys.stderr)
        return 1

    failures: list[str] = []
    cutoff = datetime.now(UTC) - MAX_STALENESS
    for symbol in SYMBOLS:
        try:
            closes = frame[symbol]["Close"].dropna()
        except (KeyError, TypeError):
            failures.append(f"{symbol}: missing from payload")
            continue
        if closes.empty:
            failures.append(f"{symbol}: no closes")
            continue
        price = float(closes.iloc[-1])
        stamp = closes.index[-1].to_pydatetime()
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        if not price > 0:
            failures.append(f"{symbol}: non-positive close {price}")
        elif stamp < cutoff:
            failures.append(f"{symbol}: stale close from {stamp.isoformat()}")
        else:
            print(f"canary: {symbol} {price:.2f} as of {stamp.isoformat()}")

    if failures:
        for failure in failures:
            print(f"canary: FAIL {failure}", file=sys.stderr)
        return 1
    print("canary: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
