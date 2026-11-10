import { formatTime } from "../lib/format";
import type { MarketSnapshot } from "../types/market-snapshot";

interface Props {
  snapshot: MarketSnapshot | undefined;
  streamConnected: boolean;
  onRefresh: () => void;
  isRefreshing: boolean;
  cooldownSeconds: number;
}

export function Header({
  snapshot,
  streamConnected,
  onRefresh,
  isRefreshing,
  cooldownSeconds,
}: Props) {
  const live = streamConnected && snapshot?.status.indexes !== "error";
  const disabled = isRefreshing || cooldownSeconds > 0;

  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="flex items-center gap-2">
          <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="#141922" />
            <path
              d="M5 22l5-7 4 4 5-9 8 12"
              fill="none"
              stroke="#00E676"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <h1 className="text-lg font-semibold tracking-tight">Market Pulse Terminal</h1>
        </div>
        <p className="mt-1 flex items-center gap-2 text-xs text-muted">
          <span className="relative flex h-2 w-2" aria-hidden="true">
            <span
              className={`absolute inline-flex h-full w-full rounded-full ${
                live ? "animate-ping bg-up/60" : "bg-muted/40"
              }`}
            />
            <span
              className={`relative inline-flex h-2 w-2 rounded-full ${
                live ? "bg-up" : "bg-muted"
              }`}
            />
          </span>
          US markets · {live ? "live snapshot" : "stale snapshot"}
          {snapshot ? (
            <span className="tabular font-mono text-muted">
              · {formatTime(snapshot.fetchedAt)}
            </span>
          ) : null}
        </p>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onRefresh}
          disabled={disabled}
          aria-live="polite"
          className="rounded-lg border border-edge bg-panel px-3 py-1.5 text-xs font-semibold text-ink transition-colors hover:bg-edge/60 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isRefreshing
            ? "Refreshing…"
            : cooldownSeconds > 0
              ? `Refresh in ${cooldownSeconds}s`
              : "Refresh"}
        </button>
      </div>
    </header>
  );
}
