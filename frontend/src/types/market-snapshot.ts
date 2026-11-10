/**
 * Generated from shared/schema/market-snapshot.schema.json by scripts/gen_types.py.
 * Do not edit: change the schema, then run ./scripts/gen_types.sh (AGENTS.md §5).
 * Wire names are camelCase, matching the JSON contract exactly.
 */

export type SectionStatus = "fresh" | "stale" | "error";
export type Verdict = "BEARISH" | "UNCERTAIN" | "NEUTRAL" | "BULLISH" | "UNKNOWN";
export type MarketStatus = "pre_market" | "regular" | "after_hours" | "closed" | "unknown";
export type ComponentName = "volatility" | "trend" | "momentum" | "riskAppetite" | "headlineTone";

/** UTC ISO-8601, always Z-suffixed. Convert to the user's locale only in the frontend (AGENTS.md §5). */
export type Timestamp = string;

/** An index symbol with a leading caret (^GSPC) or a US ticker. */
export type TickerSymbol = string;

/** Positive price; invalid rows are dropped before the snapshot is built (AGENTS.md rule 6). */
export type Price = number;

/** Percent change. The bounds are a plausibility guard, not a filter; mover thresholds live in movers_filter (FR-7). */
export type ChangePercent = number;

/** Section to provider name, recording which provider supplied each section (FR-6). Keys are section names such as indexes, movers, news, status, sentiment; values are provider identifiers such as yfinance, alpaca, finnhub. */
export type SourceMap = Record<string, string>;

/** Per-section freshness. A failed refresh keeps the last good data and marks the section stale; it never blanks the section (FR-9, AGENTS.md rule 5). */
export type SectionStatusMap = Record<string, SectionStatus>;

export interface IndexCard {
  symbol: TickerSymbol;
  label: string;
  price: Price;
  /** Absolute change for the session, signed. */
  change: number;
  changePercent: ChangePercent;
  /** true for VIX: a rise is coloured as a fall (FR-21, AGENTS.md §7). */
  invert: boolean;
  /** Normalized intraday series, about 140 points; may be shorter when history is thin. */
  sparkline: Array<number>;
  /** An ETF (SPY, QQQ, DIA, IWM, VIXY) standing in for an index. Added after the reference build, so optional; the backend always emits it (AGENTS.md rule 7). */
  isProxy?: boolean;
  /** Time this card's data was last good. */
  asOf?: Timestamp;
}

export interface Sentiment {
  /** Band containing position, or UNKNOWN when fewer than three components are available (docs/sentiment.md §4). */
  verdict: Verdict;
  /** Mood score, 0 very bearish to 100 very bullish (FR-10). */
  position: number;
  marketStatus: MarketStatus;
  /** Deterministic template text, or an LLM summary when ENABLE_LLM_SUMMARY is on (FR-12). May be empty. */
  summary: string;
  /** Up to five headlines (FR-11); empty when the news provider fails. */
  headlines: Array<Headline>;
  /** The components that fired, with effective weights summing to 1.0, so the UI can explain the score (docs/sentiment.md §3). Added after the reference build, so optional; the backend emits it on every snapshot. */
  components?: Array<Component>;
}

export interface Headline {
  title: string;
  url: string;
  source: string;
  publishedAt: Timestamp;
}

export interface Component {
  /** Component identifiers fixed by docs/sentiment.md. */
  name: ComponentName;
  /** 0 very bearish to 100 very bullish. Computed as a float internally and rounded half-up on output. */
  score: number;
  /** Effective weight after renormalising over available components; the exposed weights sum to 1.0. */
  weight: number;
}

export interface Mover {
  symbol: TickerSymbol;
  /** Company name, truncated for display. */
  name: string;
  price: Price;
  changePercent: ChangePercent;
}

export interface MostActiveRow {
  symbol: TickerSymbol;
  name: string;
  price: Price;
  changePercent: ChangePercent;
  /** Session volume. On free Alpaca this is IEX-only, which understates the consolidated market. */
  volume: number;
  dayLow: Price;
  dayHigh: Price;
}

export interface SnapshotError {
  /** Section that failed, for example indexes, movers, news or sentiment. */
  section: string;
  /** Provider that produced the error, when it is known. */
  provider?: string;
  /** Short message. Never contains keys, tokens or account identifiers (AGENTS.md rule 2). */
  message: string;
}

/** Market Pulse Terminal market snapshot (SRS §6). */
export interface MarketSnapshot {
  /** Contract version. Removing or renaming a field needs a version bump, a migration note and an update to the static-export fallback (AGENTS.md §5). */
  schemaVersion: 1;
  /** UTC ISO-8601 time the snapshot was built (FR-8). */
  fetchedAt: Timestamp;
  /** Header index cards in display order (FR-19). */
  indexes: Array<IndexCard>;
  sentiment: Sentiment;
  /** Top gainers, best first (reference shows up to 10 rows). */
  gainers: Array<Mover>;
  /** Top losers, worst first. */
  losers: Array<Mover>;
  /** Most active by volume, with the day range needed by row tooltips (FR-25). */
  mostActive: Array<MostActiveRow>;
  /** Section to provider name, recording which provider supplied each section (FR-6). Keys are section names such as indexes, movers, news, status, sentiment; values are provider identifiers such as yfinance, alpaca, finnhub. */
  sources: SourceMap;
  /** Per-section freshness. A failed refresh keeps the last good data and marks the section stale; it never blanks the section (FR-9, AGENTS.md rule 5). */
  status: SectionStatusMap;
  /** Delay of the slowest contributing feed, disclosed in the footer with the provider list (AGENTS.md §12). */
  feedDelaySeconds: number;
  /** Non-fatal problems recorded while building the snapshot; empty when everything succeeded. */
  errors: Array<SnapshotError>;
}
