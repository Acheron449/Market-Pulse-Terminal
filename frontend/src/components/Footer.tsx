import { formatTime } from "../lib/format";
import type { MarketSnapshot } from "../types/market-snapshot";

interface Props {
  snapshot: MarketSnapshot | undefined;
  disclaimer: string;
}

export function Footer({ snapshot, disclaimer }: Props) {
  const providers = snapshot ? [...new Set(Object.values(snapshot.sources))].join(", ") : "—";
  const delay = snapshot?.feedDelaySeconds ?? 0;

  return (
    <footer className="border-t border-edge pt-4 text-[11px] leading-relaxed text-muted">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p>
          Data as of{" "}
          <span className="tabular font-mono text-ink/80">
            {formatTime(snapshot?.fetchedAt)}
          </span>{" "}
          via {providers}
          {snapshot ? (
            <span>
              {" "}
              ·{" "}
              {delay > 0
                ? `delayed up to ${Math.round(delay / 60)} minutes`
                : "real-time where the feed allows"}
            </span>
          ) : null}
        </p>
        <p>
          Charting by{" "}
          <a
            href="https://www.tradingview.com/"
            target="_blank"
            rel="noreferrer noopener"
            className="underline-offset-2 hover:text-volume hover:underline"
          >
            TradingView
          </a>
        </p>
      </div>
      <p className="mt-2 max-w-3xl">{disclaimer}</p>
    </footer>
  );
}
