import type { MarketStatus } from "../types/market-snapshot";

export function StaleBadge({ label = "STALE" }: { label?: string }) {
  return (
    <span
      className="rounded border border-caution/40 bg-caution/10 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-caution"
      title="This section is showing its last good data; the latest refresh failed."
    >
      {label}
    </span>
  );
}

export function ProxyBadge() {
  return (
    <span
      className="rounded border border-volume/40 bg-volume/10 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-volume"
      title="An ETF standing in for the index; the price is the ETF's, not the index level."
    >
      PROXY
    </span>
  );
}

const STATUS_LABEL: Record<MarketStatus, string> = {
  pre_market: "PRE-MARKET",
  regular: "MARKET OPEN",
  after_hours: "AFTER HOURS",
  closed: "MARKET CLOSED",
  unknown: "STATUS UNKNOWN",
};

const STATUS_TONE: Record<MarketStatus, string> = {
  pre_market: "border-caution/40 text-caution",
  regular: "border-up/40 text-up",
  after_hours: "border-volume/40 text-volume",
  closed: "border-edge text-muted",
  unknown: "border-edge text-muted",
};

export function StatusChip({ status }: { status: MarketStatus }) {
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold tracking-widest ${STATUS_TONE[status]}`}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}
