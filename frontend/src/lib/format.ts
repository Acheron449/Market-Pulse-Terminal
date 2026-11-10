/**
 * All number formatting lives here (FR-20, AGENTS.md §7); components never reimplement it.
 */

export const EM_DASH = "—";

export type Tone = "up" | "down" | "flat";

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Two decimals with thousands separators, or an em dash for invalid input. */
export function formatPrice(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) return EM_DASH;
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Signed two-decimal number: "+1.23" / "-4.50" / em dash. */
export function formatSigned(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) return EM_DASH;
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatPrice(value)}`;
}

/** Signed percent, clamped display at the contract's plausibility range. */
export function formatPercent(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) return EM_DASH;
  return `${formatSigned(value)}%`;
}

/** Volume as K/M/B, with an em dash for invalid input. */
export function formatVolume(value: number | null | undefined): string {
  if (!isFiniteNumber(value) || value < 0) return EM_DASH;
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return Math.round(value).toString();
}

/**
 * Colour direction, honouring `invert` for VIX: a rising VIX is bearish (FR-21).
 * The sign and arrow are always rendered too, so colour is never the only signal.
 */
export function toneFor(changePercent: number | null | undefined, invert = false): Tone {
  if (!isFiniteNumber(changePercent) || changePercent === 0) return "flat";
  const rising = changePercent > 0;
  return (invert ? !rising : rising) ? "up" : "down";
}

export const toneClasses: Record<Tone, string> = {
  up: "text-up",
  down: "text-down",
  flat: "text-muted",
};

export const toneBgClasses: Record<Tone, string> = {
  up: "bg-up",
  down: "bg-down",
  flat: "bg-muted",
};

/** Direction arrow for accessibility: colour is never the only cue (NFR-7). */
export function arrowFor(changePercent: number | null | undefined): string {
  if (!isFiniteNumber(changePercent) || changePercent === 0) return "→";
  return changePercent > 0 ? "▲" : "▼";
}

/** Localised clock time for "data as of" lines. */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return EM_DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return EM_DASH;
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Whole seconds between an ISO timestamp and now, or null. */
export function ageSeconds(iso: string | null | undefined, now = Date.now()): number | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return Math.max(0, Math.round((now - date.getTime()) / 1000));
}

/** Truncate a company name for a dense row. */
export function truncate(value: string, max = 18): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

/** Value normalised to 0..1 inside a min/max window, for sparklines and bars. */
export function normalise(values: number[]): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (!Number.isFinite(min) || !Number.isFinite(max) || max === min) {
    return values.map(() => 0.5);
  }
  return values.map((value) => (value - min) / (max - min));
}
