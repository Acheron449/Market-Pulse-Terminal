# Market Pulse Terminal — Software Requirements Specification

Version 1.0 (Draft) · 8 November 2026 · Derived from the attached Perplexity Finance reference build · Timeline: [TIMELINE.md](./TIMELINE.md)

## 1. Introduction

### 1.1 Purpose

This document specifies the requirements for **Market Pulse Terminal (MPT)**: a self-hosted, auto-updating US markets dashboard that reproduces the look and behaviour of the attached Perplexity Finance example, but sources its data from Python libraries and public or API-based providers (yfinance, Alpaca, Finnhub, and optionally TradingView widgets) instead of Perplexity.

### 1.2 Scope

MPT is a read-only, single-page web application plus a Python backend. It shows major index cards, a market-mood gauge, top gainers, top losers and most-active stocks and a chart drill-down for any symbol, and keeps them current without user action. It does not place trades, manage accounts or give investment advice.

### 1.3 What the reference build tells us

The zip contains a compiled Vite/React bundle, a `market-data.json` snapshot and an `index.html`. Because the source is minified, the UI must be rebuilt; the bundle serves as a visual and behavioural specification. Findings:

| Area | Observed in the reference |
| --- | --- |
| Stack | React, Tailwind, shadcn/Radix (tooltips, toasts), TanStack Query, wouter (hash routing), dark theme by default |
| Data flow | Calls `/api/market` (6 s timeout, `?refresh=1` for a manual refresh). On failure it falls back to the static `market-data.json` and marks the data as not live |
| Header | Logo, title "Market Pulse Terminal", subtitle "US markets · live snapshot", pulsing live dot and localized timestamp |
| Index cards | Five cards: S&P 500 (^GSPC), NASDAQ (^IXIC), DOW JONES (^DJI), RUSSELL 2000 (^RUT), VIX (^VIX). Each shows price, absolute and percent change, and a 140-point sparkline. VIX has `invert: true`, so a rise is coloured red |
| Market mood | Gradient gauge with needle (position 0–100, clamped 2–98), verdict (BEARISH, UNCERTAIN, NEUTRAL, BULLISH, UNKNOWN), market-status chip (e.g. AFTER HOURS), summary text and up to a few headline links |
| Movers | Three columns, TOP GAINERS, TOP LOSERS and MOST ACTIVE (up to 10 rows). Each row has rank, symbol, truncated name, price, percent change or volume (K/M/B), and a relative bar. Hovering a row shows day low/high/volume |
| Footer | "Data as of … via \<provider>" and a Refresh button with spinner |
| Resilience | Skeleton loaders, error card with Retry, and a banner when `errors[]` is non-empty |
| Palette | Up #00E676, down #FF5252, caution #F0B429, volume #22D3EE, monospace tabular numerals |

Gaps in the sample data we must handle: `sentiment.summary` is empty and `headlines` is empty, only 8 losers were returned, and the snapshot contains micro-cap and 3× leveraged ETF names that a production filter should control.

### 1.4 Definitions

**Snapshot**: the complete JSON document the UI renders. **Provider**: an adapter around one data source. **Capability**: one kind of data (quotes, series, movers, status, news). **IEX / SIP**: a single exchange feed versus the consolidated US feed. **Stale**: data older than its freshness budget.

## 2. Product Overview

### 2.1 Users

Primary: individual investors and developers who want a free, glanceable, self-hosted market overview. Secondary: teams embedding the dashboard on an internal screen.

### 2.2 Assumptions and constraints

- Free-tier data only for v1. Free tiers carry rate limits, delays and non-commercial terms (see section 4.3).
- Provider API keys live only on the server.
- US equities and the five headline indices only. International markets, crypto and futures are out of scope for v1.
- Python 3.12+, Node 20+.

### 2.3 Out of scope for v1

Trading or order entry, user accounts, portfolios and watchlists, options data, alerts, mobile native apps, redistribution of data to third parties.

## 3. System Architecture

```
[yfinance] [Alpaca] [Finnhub]            [TradingView widgets*]
     \        |        /
      Provider Registry (capability routing, failover, circuit breaker, rate limiter)
                 |
   Scheduler (market-hours aware) --> Snapshot Builder --> Sentiment Engine
                 |
        Cache (memory + SQLite: last-good snapshot, bar cache)
                 |
   FastAPI: /api/market · /api/stream (SSE) · /api/health · /api/chart/* (datafeed)
                 |
   React SPA: dashboard (TanStack Query + SSE)
              chart panel (Lightweight Charts by default, or TradingView
              Advanced Charts through the datafeed adapter)
              optional static market-data.json export
```

\*TradingView widgets run client-side and show TradingView's own data. TradingView charts (Lightweight Charts, or Advanced Charts if licensed) are rendering libraries fed by our backend through the datafeed adapter; see 4.2 and 4.4.

**Key decisions.** (1) The JSON contract in section 6 extends the reference schema so the UI port is mechanical. (2) The backend is the only component that talks to providers. (3) Every section of the snapshot carries its own freshness so partial failure degrades gracefully. (4) A static-export mode lets the app run on static hosting with a scheduled job writing `market-data.json`, mirroring the reference's fallback.

## 4. Data Sources and Provider Strategy

### 4.1 Capability matrix

| Capability | Primary | Fallback | Notes |
| --- | --- | --- | --- |
| Index quotes (^GSPC, ^IXIC, ^DJI, ^RUT, ^VIX) | yfinance | ETF proxies via Alpaca or Finnhub (SPY, QQQ, DIA, IWM, VIXY) | Free Finnhub and Alpaca equity feeds do not carry index levels, so proxies must be labelled as proxies and never shown as index values |
| Intraday sparkline series (about 140 points) | yfinance (5-minute history) | Alpaca bars on proxy ETFs | Normalize to a fixed-length array |
| Top gainers, losers, most active | Alpaca screener (movers and most-actives endpoints) | yfinance predefined screeners | Verify availability on the free plan in the Phase 0 spike |
| Market status (open, pre, after hours, closed) | Alpaca clock and calendar | Finnhub market-status, then local NYSE calendar | Local calendar is the last resort |
| Headlines | Finnhub market news | Alpaca news | Free tier returns general market news |
| Live push (optional) | Alpaca or Finnhub WebSocket | Polling | Alpaca free tier streams IEX data with a 30-symbol cap |

### 4.2 TradingView integration: charts, not data

TradingView supplies the **chart interface**, never the data. Its Advanced Charts library runs in the browser and includes no market data: the host application implements the library's Datafeed API (symbol search, symbol resolution, historical bars, live bar subscriptions), and MPT's backend answers those calls from yfinance, Alpaca and Finnhub. Quotes, depth of market and order entry belong to TradingView's separate Trading Platform product and are out of scope here. TradingView still has no official public market-data API, so scraping libraries remain out of scope and a server-side TradingView data client is prohibited.

| Option | What it gives | Access and terms | Role in MPT |
| --- | --- | --- | --- |
| Lightweight Charts | Open-source canvas charts (line, area, candles, histogram); no built-in indicators or drawing tools; you pass in the series | Apache-2.0 via npm, currently 5.x (`chart.addSeries(LineSeries)`; the v4 `addLineSeries` family is gone). The licence requires the notice from the `NOTICE` file plus a link to tradingview.com on a page users see | **Default** drill-down chart in every deployment |
| Advanced Charts | Full charting UI with built-in studies, drawing tools, chart types and themes; data through the Datafeed API | Free **only** for a public, free-to-access implementation. TradingView's FAQ states no licence is issued for personal, hobby, study or test use; the Free Advanced Charts Agreement adds that the files must not be hosted in a public code repository and that TradingView gets free unlimited access to verify the deployment. Access comes from an application and a signed agreement, not an npm install | **Optional upgrade** for public deployments, behind `CHART_ENGINE=advanced` |
| Free embeddable widgets | Ticker tape, mini chart and similar, showing TradingView's own data | Free with TradingView attribution; served by TradingView, not by us | Optional ticker-tape strip behind a flag (FR-27) |
| Trading Platform and Broker API | Order ticket, watchlist, depth of market | Separate licence | Out of scope; MPT is read-only |

**Decision rule**

- Private, personal or internal deployment: use Lightweight Charts only, at a pinned 5.x version. Do not apply for Advanced Charts; the licence does not cover this case.
- Public deployment: confirm in Phase 0 that the site is public and free to access (no paywall, no login gate on the chart), then apply for Advanced Charts and sign the Free Advanced Charts Agreement in week 1. Build against the `ChartPanel` abstraction on Lightweight Charts meanwhile and switch by configuration when access arrives. If access is refused or late, ship Lightweight Charts publicly; nothing in the product depends on Advanced Charts.
- The Advanced Charts files are proprietary. Never commit them or bake them into a public image; a script installs them into a git-ignored folder (`ADVANCED_CHARTS_PATH`), and CI must build and pass without them.
- Keep the TradingView attribution visible in both engines. It is the condition of the free licence, not a themeable decoration.
- Pin the library version and implement against the `datafeed-api.d.ts` that ships with it. The published docs are versioned and the API changes between majors.
- The charting licence does not cover market data. A public site showing free-tier yfinance or Finnhub data may breach those providers' terms (see 11).
- Endpoint contracts, field mapping and build order are specified in [tradingview.md](./tradingview.md).

### 4.3 Provider constraints to design for

- **yfinance**: an unofficial wrapper over Yahoo Finance endpoints. It can break without notice, rate-limit or block, and Yahoo's terms generally restrict it to personal use. Use polite polling, caching and a single shared session.
- **Alpaca (free Basic plan)**: real-time IEX-only data, with full SIP data only older than 15 minutes unless a paid plan is held; about 200 historical REST calls per minute; 30 WebSocket symbols. Volume and prices from IEX under-represent the consolidated market, so "most active" by volume needs the SIP feed or a disclosed caveat.
- **Finnhub (free)**: about 60 calls per minute (30 per second burst), real-time US quotes, personal non-commercial use. News-sentiment is premium and the candle endpoint has been reported as restricted on free keys, so MPT does not depend on either.
- Limits change. Re-verify them in the Phase 0 spike and record results in [provider-notes.md](./provider-notes.md).

### 4.4 Chart datafeed adapter

A thin TypeScript adapter (`frontend/src/chart/datafeed.ts`) maps the backend's chart endpoints onto TradingView's Datafeed API, and the Lightweight Charts panel reads the same endpoints, so both engines share one data path. Endpoint payloads stay camelCase per section 6; the adapter is the only place that speaks TradingView's snake_case field names. Contracts and build order are in [tradingview.md](./tradingview.md).

| Datafeed API call | MPT behaviour | Backend |
| --- | --- | --- |
| `onReady` | Return a `DatafeedConfiguration`: `supported_resolutions` (`1`, `5`, `15`, `60`, `1D`), exchanges, symbol types, currency codes, `supports_search: true`, `supports_group_request: false`, `supports_marks: false`, `supports_time: true` | `GET /api/chart/config` |
| `searchSymbols` | Search a curated US universe (indices, ETFs, symbols seen in movers) and validate typed tickers with a provider | `GET /api/chart/symbols?query=` |
| `resolveSymbol` | Return a complete symbol descriptor and map it to `LibrarySymbolInfo`: `name`/`ticker`, `listed_exchange`, `type`, `currency_code`, `timezone: America/New_York`, `session`, `subsessions`/`subsession_id`, `session_holidays`, `corrections`, `minmov`/`pricescale`, `format: price`, `visible_plots_set`, `has_intraday`/`intraday_multipliers`, `has_daily`/`daily_multipliers`, `supported_resolutions`, `data_status`/`delay` | `GET /api/chart/symbols/{symbol}` |
| `getBars` | Return every bar in `[from, to)` in ascending order, topped up backwards until `countBack` is satisfied, never fewer than two bars, with `noData: true` only once older history is genuinely exhausted | `GET /api/chart/history` |
| `subscribeBars` / `unsubscribeBars` | Push whole bars for the newest period to every callback matching the subscription; keyed by symbol, resolution, currency and chart type, not by symbol alone | `GET /api/chart/stream` (SSE) |
| `getServerTime` | Optional: return server time in seconds so the bar countdown does not follow a skewed browser clock | `GET /api/chart/time` |

Quotes, depth and the other Trading Platform methods (`getQuotes`, `subscribeQuotes`, `subscribeDepth`) are not required by Advanced Charts and are out of scope for v1.

Rules:

1. **Units.** In the Datafeed API, bar `time` and `nextTime` are epoch **milliseconds** UTC; `PeriodParams.from`/`to`, mark times and server time are **seconds**. Daily, weekly and monthly bars are stamped 00:00:00 UTC, not at the session open. Convert in the adapter, and test the conversion.
2. **History contract.** `getBars` returns all bars in the requested range, extends backwards past `from` when the range holds fewer than `countBack` bars, returns more than `countBack` rather than truncating, and returns at least two bars whenever they exist. `noData` ends the paging; `nextTime` is legacy.
3. **Resolutions.** Declare resolutions twice: in `DatafeedConfiguration.supported_resolutions` and in each symbol's `supported_resolutions`. Intraday needs `has_intraday: true` plus `intraday_multipliers`; daily needs `has_daily: true` plus `daily_multipliers`; hours are requested as minutes (`60`), days as `1D`. The library may build 30-minute or 2-hour bars from 1-minute data; keep that unless a provider's bars are off the session anchor, in which case disable it with the `disable_resolution_rebuild` featureset.
4. **Sessions and the calendar.** `session` is exchange-local and its last time is non-inclusive: `0930-1600` runs Monday to Friday. Pre- and post-market periods come from `subsessions` (`regular`, `premarket`, `postmarket`) with `subsession_id` set to the period on screen. Non-trading days come from `session_holidays` (YYYYMMDD) and early closes from `corrections` (`0930-1300:20261127`), both generated from the calendar service in section 9 — never hand-maintained. A correction overrides a holiday for the same date. Bar timestamps anchor to the session open, so intraday bars must align to 09:30, not to the hour.
5. **Symbol info.** `name`, `session`, `timezone`, `listed_exchange`, `minmov`, `pricescale`, `format` and `type` are required; send `minmove2: 0` and `fractional: false`. Use `visible_plots_set: "ohlcv"` where volume exists and `"ohlc"` (or `"c"`) for index symbols that have none. Describe ETF proxies as proxies in `description`/`long_description` and badge them in our own panel header; the library cannot badge them for us.
6. **Data status.** `data_status` is one of `streaming`, `endofday`, `delayed_streaming`; the delayed case also requires `delay` in seconds and the `display_data_mode` featureset. Derive both from the snapshot's `feedDelaySeconds` and the section `status`, and keep the feed-type chip beside the chart.
7. **Subscriptions.** A subscription is identified by symbol, resolution, currency and chart type, and several can be live at once while the user switches. Run one upstream stream per symbol and fan out to every `subscriberUID`; push complete OHLCV bars for the newest period only; never rewrite history through `subscribeBars` (use `resetCache()` and `chart.resetData()`); expect `unsubscribeBars` up to about five seconds late and keep sending until it arrives. Cap concurrent chart subscriptions (`CHART_LIVE_SUBSCRIPTION_CAP`) well below Alpaca's 30-symbol free stream limit.
8. **Bars cache and quota.** Cache bars by symbol, resolution and range; coalesce identical in-flight requests; update the quota estimate in [provider-notes.md](./provider-notes.md) when this adds calls.
9. **Bar sources.** Alpaca bars first (long history, about 200 REST calls per minute on the free plan), yfinance second. yfinance limits fine-grained intraday history to recent days or weeks; confirm exact limits in the Phase 0 spike. The Finnhub candle endpoint is not relied on because it has been reported as restricted on free keys. Index symbols (^GSPC and the rest) come from yfinance only.
10. **Frontend.** Card sparklines stay lightweight inline SVG built from the snapshot. The chart panel is code-split and loads only when a card or mover row is clicked, and it carries skeleton, stale, error and Retry states like the rest of the dashboard.
11. **Widget construction.** `new TradingView.widget(...)` needs `container`, `library_path`, `datafeed`, `symbol`, `interval`, `timezone`, `locale`, `theme` and `autosize`. MPT has no user accounts, so disable the `header_saveload` featureset rather than wiring `charts_storage_url`/`client_id`/`user_id`.
12. **Free widgets (FR-27).** The ticker tape is a third-party iframe showing TradingView's own data: allow its host in the CSP, label the strip as TradingView data, keep it out of the snapshot `sources`, and hide it in static-export and replay modes.

## 5. Functional Requirements

Priority uses MoSCoW: **M** must, **S** should, **C** could.

### 5.1 Data ingestion

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-1 | Define a `MarketDataProvider` interface with the capabilities in 4.1; each provider declares which it supports | M |
| FR-2 | Implement yfinance, Alpaca and Finnhub providers behind that interface | M |
| FR-3 | The registry routes each capability through an ordered provider list, failing over on error, timeout or invalid data | M |
| FR-4 | Each provider has a token-bucket rate limiter and a circuit breaker (open after N consecutive failures, half-open probe after a cool-down) | M |
| FR-5 | Validate every record (price > 0, finite numbers, percent change within plausible bounds, non-empty symbol) and drop or flag invalid rows | M |
| FR-6 | Record which provider supplied each section in the snapshot `sources` field | M |
| FR-7 | Movers filters are configurable: minimum price, minimum volume, exclude warrants and rights, and optionally exclude leveraged ETFs | S |

### 5.2 Snapshot and sentiment

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-8 | Build a snapshot matching section 6, with `fetchedAt` in UTC ISO-8601 | M |
| FR-9 | Retain the last good value of each section; a failed refresh must never blank a section | M |
| FR-10 | Compute the market-mood score, verdict and position per section 10 | M |
| FR-11 | Attach up to 5 headlines with title, source, URL and timestamp | S |
| FR-12 | Optionally generate a 1–2 sentence summary with an LLM, off by default, cached per snapshot, with a hard daily call cap and a deterministic template fallback | C |

### 5.3 Auto-update

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-13 | A scheduler refreshes each section on the cadences in section 9, driven by market status | M |
| FR-14 | The backend pushes new snapshots to browsers over Server-Sent Events | S |
| FR-15 | The frontend falls back to polling `/api/market` every 30 s when SSE is unavailable, and pauses while the tab is hidden | M |
| FR-16 | `GET /api/market?refresh=1` forces a rebuild, subject to a per-client cooldown (default 10 s) | M |
| FR-17 | Static-export mode writes `market-data.json` atomically after each cycle | S |
| FR-18 | On cold start, serve the persisted last-good snapshot immediately while a fresh build runs | M |

### 5.4 User interface

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-19 | Reproduce the layout in section 7.2: header, five index cards, market-mood panel, three mover columns, footer | M |
| FR-20 | Number formatting: two decimals, signed changes, K/M/B volume, em dash for invalid values | M |
| FR-21 | Colour semantics honour `invert` (VIX) | M |
| FR-22 | Animate gauge needle and flash price cells briefly when a value changes, respecting `prefers-reduced-motion` | S |
| FR-23 | Show a per-section stale badge when `status` is `stale`, and the existing "some sections couldn't load" banner when any section is `error` | M |
| FR-24 | Show a skeleton on first load and an error card with Retry when no data exists at all | M |
| FR-25 | Row tooltips show day low, day high and volume | S |
| FR-26 | Light and dark themes, dark by default | C |
| FR-27 | Optional TradingView ticker-tape widget behind a feature flag | C |
| FR-28 | A chart drill-down opens from any index card or mover row: code-split panel, 1/5/15/60-minute and 1-day resolutions, correct sessions, holidays and early closes, with skeleton, stale, error and Retry states | S |
| FR-29 | The chart discloses feed type and delay (`data_status`/`delay` derived from `feedDelaySeconds`), labels ETF proxies as proxies, and keeps TradingView attribution visible wherever its libraries or widgets render | M |

## 6. Data Contract

The schema is the single source of truth (`shared/schema/market-snapshot.schema.json`); backend models and frontend types are generated from it. Fields marked new extend the reference. Values in the example below are placeholders that show shape only: the schema enforces non-empty symbols, positive prices and bounded percent changes (`AGENTS.md` rule 6), so the block is illustrative rather than valid data as written.

```json
{
  "schemaVersion": 1,
  "fetchedAt": "2026-11-09T15:04:05Z",
  "indexes": [{
    "symbol": "^GSPC", "label": "S&P 500",
    "price": 7475.46, "change": -25.12, "changePercent": -0.33,
    "invert": false, "sparkline": [7474.4, 7496.4],
    "isProxy": false,
    "asOf": "2026-11-09T15:04:00Z"
  }],
  "sentiment": {
    "verdict": "NEUTRAL", "position": 54,
    "marketStatus": "regular",
    "summary": "",
    "headlines": [{"title": "", "url": "", "source": "", "publishedAt": ""}],
    "components": [
      {"name": "volatility", "score": 51, "weight": 0.3},
      {"name": "trend", "score": 62, "weight": 0.25},
      {"name": "momentum", "score": 58, "weight": 0.2},
      {"name": "riskAppetite", "score": 43, "weight": 0.15},
      {"name": "headlineTone", "score": 55, "weight": 0.1}
    ]
  },
  "gainers":    [{"symbol": "", "name": "", "price": 0, "changePercent": 0}],
  "losers":     [{"symbol": "", "name": "", "price": 0, "changePercent": 0}],
  "mostActive": [{"symbol": "", "name": "", "price": 0, "changePercent": 0,
                  "volume": 0, "dayLow": 0, "dayHigh": 0}],
  "sources": {"indexes": "yfinance", "movers": "alpaca", "news": "finnhub"},
  "status":  {"indexes": "fresh", "movers": "stale", "sentiment": "fresh"},
  "feedDelaySeconds": 0,
  "errors": []
}
```

`marketStatus` values: `pre_market`, `regular`, `after_hours`, `closed`, `unknown`. `status` values: `fresh`, `stale`, `error`. `errors[]` entries carry `section`, `provider` and a short message with no secrets.

## 7. External Interfaces

### 7.1 HTTP API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/market` | Latest snapshot (`?refresh=1` to force) |
| `GET /api/stream` | SSE stream: `snapshot` event on connect, then on each change; heartbeat every 15 s |
| `GET /api/health` | Per-provider state (circuit status, last success, remaining quota) and per-section age |
| `GET /api/config` | Non-secret flags for the UI (feature flags, refresh cooldown, data-delay disclosure) |

### 7.2 UI layout

Max width 1320 px. Index cards in a 2/3/5-column grid by breakpoint. Mood panel below, stacking on mobile. Three mover cards in a 3-column grid collapsing to one column. Monospace tabular figures for all numbers. Footer text reads "Data as of \<time> via \<provider list>".

### 7.3 Provider interfaces

REST and WebSocket clients use `httpx` and `websockets` with explicit timeouts (default 5 s connect, 8 s read).

## 8. Non-Functional Requirements

| ID | Category | Requirement |
| --- | --- | --- |
| NFR-1 | Performance | `/api/market` p95 under 150 ms from cache; first contentful paint under 1.5 s on broadband |
| NFR-2 | Freshness | During regular hours, quotes no older than 60 s and movers no older than 120 s under normal provider health |
| NFR-3 | Availability | UI shows data (possibly stale) even if all providers are down; target 99.5% backend uptime |
| NFR-4 | Resilience | Any single provider outage causes no section to go blank; failover completes within one refresh cycle |
| NFR-5 | Quota safety | Total calls stay under 70% of each provider's documented limit; verified by a metrics test |
| NFR-6 | Security | Keys only in environment or secret store, never logged or sent to the browser; CORS restricted; refresh endpoint rate-limited; dependencies audited in CI |
| NFR-7 | Accessibility | WCAG 2.1 AA: colour is never the only change indicator (signs and arrows included), keyboard-reachable tooltips, ARIA labels on cards and gauge |
| NFR-8 | Observability | Structured JSON logs, Prometheus-style metrics (provider latency, error counts, snapshot age), optional Sentry |
| NFR-9 | Portability | Docker Compose one-command run; also deployable as static export plus scheduled job |
| NFR-10 | Maintainability | Adding a provider requires one new file and one registry entry; 80%+ coverage on backend core |
| NFR-11 | Browser support | Latest two versions of Chrome, Safari, Firefox, Edge; mobile viewport from 360 px |

## 9. Update and Refresh Policy

| Section | Regular hours | Pre / after hours | Closed |
| --- | --- | --- | --- |
| Index quotes | 15–30 s | 60 s | 15 min |
| Sparklines | 5 min | 10 min | once at close |
| Movers and most active | 60 s | 2–5 min | 30 min |
| Market status | 60 s | 60 s | 15 min, recheck at next open |
| Headlines | 5 min | 10 min | 30 min |
| Mood recompute | with each quotes refresh | with each refresh | once |

Cadences are configurable. The scheduler adds jitter, skips a cycle if the previous one is still running, and backs off exponentially after failures. Market holidays and early closes come from the Alpaca calendar, with a bundled NYSE calendar as fallback.

## 10. Market-Mood Methodology

Perplexity's verdict is proprietary, so MPT computes its own transparent composite. Score 0 (very bearish) to 100 (very bullish), shown as `position`.

| Component | Default weight | Logic |
| --- | --- | --- |
| Volatility | 30% | VIX percentile over one year (inverted) and today's VIX change |
| Trend | 25% | S&P 500 distance from its 50-day average |
| Day momentum | 20% | Average percent change of the four equity indices |
| Risk appetite | 15% | Russell 2000 versus S&P 500 relative move |
| Headline tone | 10% | Optional lexicon-based score over recent headlines; weight redistributes if disabled |

Verdict bands (configurable): 0–25 BEARISH, 26–44 UNCERTAIN, 45–60 NEUTRAL, 61–100 BULLISH, and UNKNOWN when fewer than three components are available. The `components` array is exposed so the UI can explain the score. The panel must state that the mood is a heuristic and not advice. Formulas, worked examples, missing-data rules and the calibration log are in [sentiment.md](./sentiment.md).

## 11. Legal and Compliance

- Display a footer disclaimer: informational only, not investment advice.
- Disclose data delay and feed type (for example "IEX feed" or "data may be delayed up to 15 minutes") using `feedDelaySeconds` and the provider list.
- Respect each provider's terms. The free tiers of Finnhub and Yahoo-based data are for personal use; public or commercial deployment needs paid or licensed data, and redistributing raw data via the public API may be restricted.
- Provide TradingView attribution wherever its widgets appear.
- Do not copy Perplexity branding, text or proprietary assets; the reference supplies layout and behaviour only.

## 12. Testing and Acceptance

### 12.1 Test strategy

- **Unit**: validators, sentiment maths, market-hours logic, formatting helpers.
- **Contract**: recorded provider responses (fixtures) mapped into the snapshot, plus JSON-schema validation of every API response. No test calls a live provider.
- **Failure injection**: timeouts, 429s, malformed JSON, empty movers, provider returning stale timestamps.
- **Frontend**: component tests for cards and rows; Playwright end-to-end covering load, live update, stale badge, error card and refresh cooldown.
- **Soak**: five consecutive trading days on staging with zero unhandled errors and no quota breaches.

### 12.2 Acceptance criteria for v1.0

1. With valid keys, a fresh install renders all five index cards, mood panel and three mover columns within 10 s.
2. During market hours values change without a page reload at the configured cadence.
3. Disabling any one provider leaves every section populated, with failover visible in `/api/health`.
4. Disabling all providers shows the last-good snapshot with stale badges, never a blank page.
5. Pre-market, after-hours, weekend and holiday states display the correct status chip and slowed cadence.
6. No API key appears in browser traffic, logs or the built frontend.
7. Lighthouse accessibility score of 95 or higher; all NFRs in section 8 verified.

## 13. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| yfinance breaks or is blocked | High | High | Never the sole source for movers; failover, cached last-good data, version pinning, canary test in CI |
| Free-tier IEX data misrepresents volume and movers | High | Medium | Disclose feed; use delayed SIP or screener endpoints where possible; filters for illiquid names |
| Rate-limit exhaustion | Medium | Medium | Token buckets, shared cache, quota metrics, 70% budget rule |
| Terms-of-service violation on public hosting | Medium | High | Personal-use default; documented upgrade path to licensed data; no TradingView scraping |
| Garbage movers (penny stocks, bad ticks) | High | Medium | Validation and configurable filters |
| Sentiment seen as advice | Low | High | Methodology transparency and disclaimer |
| Holiday and half-day edge cases | Medium | Low | Calendar-driven status, tests for Thanksgiving week |

## 14. Open Questions

1. Will the app stay personal-use, or be public? This decides whether paid data licences are required.
2. Should leveraged ETFs and sub-$1 stocks appear in movers (the reference includes them)?
3. Is an LLM-written summary wanted, and which budget cap applies?
4. Preferred hosting: single container, or static site plus scheduled export?
5. Is a Python-only UI alternative (for example Streamlit) acceptable for a prototype? This SRS assumes React to match the reference.

## Appendix A. Configuration Variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `ALPACA_API_KEY`, `ALPACA_API_SECRET` | Alpaca credentials | none |
| `ALPACA_FEED` | `iex` or `sip` | `iex` |
| `FINNHUB_API_KEY` | Finnhub key | none |
| `PROVIDER_ORDER_INDEXES`, `_MOVERS`, `_NEWS`, `_STATUS` | Failover order per capability | see 4.1 |
| `REFRESH_COOLDOWN_SECONDS` | Manual refresh limit | 10 |
| `MOVERS_MIN_PRICE`, `MOVERS_MIN_VOLUME` | Mover filters | 1.00, 100000 |
| `ENABLE_LLM_SUMMARY`, `ANTHROPIC_API_KEY` | Optional summary | off |
| `SENTIMENT_WEIGHTS` | Component weights, renormalised over available components | `volatility=0.30,trend=0.25,momentum=0.20,risk_appetite=0.15,headline_tone=0.10` |
| `SENTIMENT_BANDS` | Verdict band upper bounds, inclusive | `bearish=25,uncertain=44,neutral=60` |
| `SENTIMENT_MIN_COMPONENTS` | Components required before the verdict falls back to `UNKNOWN` | 3 |
| `ENABLE_HEADLINE_TONE` | Lexicon headline-tone component | on |
| `ENABLE_STATIC_EXPORT`, `STATIC_EXPORT_PATH` | Write `market-data.json` | off |
| `CHART_ENGINE` | Chart implementation: `lightweight` or `advanced` | `lightweight` |
| `CHART_RESOLUTIONS` | Resolutions advertised to the chart | `1,5,15,60,1D` |
| `CHART_LIVE_SUBSCRIPTION_CAP` | Max concurrent chart bar subscriptions | 10 |
| `ADVANCED_CHARTS_PATH` | Git-ignored folder holding the licensed library files | unset |
| `ENABLE_TRADINGVIEW_WIDGET` | UI widget flag | off |
| `CORS_ORIGINS` | Allowed origins | localhost only |
