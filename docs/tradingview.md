# TradingView implementation plan

Companion to the [SRS](./SRS.md) §4.2 (engine selection and licensing) and §4.4 (datafeed adapter rules). Requirement IDs come from the SRS. The snapshot contract stays in `shared/schema/market-snapshot.schema.json`; nothing in this document changes it.

Version 1.0 (Draft) · 8 November 2026 · Owner: chart workstream

## 1. Scope

In scope (FR-28, FR-29):

- A drill-down chart for any symbol already on the dashboard: the five indices and any mover row.
- Resolutions: 1, 5, 15 and 60 minutes, plus 1 day.
- Regular, pre-market and post-market sessions; holidays and early closes from the calendar service in SRS §9.
- Honest delay and feed disclosure, ETF-proxy labelling, and TradingView attribution.

Out of scope: order entry, watchlists, depth of market, saved chart layouts, quotes, and any request the browser or backend makes to TradingView for data. TradingView supplies rendering only (§4.2; `AGENTS.md` rule 8).

## 2. Engine choice

| Engine | Setting | Condition |
| --- | --- | --- |
| Lightweight Charts 5.x | `CHART_ENGINE=lightweight` (default) | Always available. Apache-2.0, no application needed |
| Advanced Charts | `CHART_ENGINE=advanced` | Public, free-to-access deployment, with the Free Advanced Charts Agreement signed |

Both implementations sit behind `ChartPanel` and read the same four endpoints, so the choice is configuration only.

Licensing rules that constrain the build:

- Advanced Charts is free **only** for a public implementation that stays free to access. TradingView's FAQ states no licence is issued for personal, hobby, study or test use, including private or internal deployments. The Free Advanced Charts Agreement (v.0626) adds that the library files must not be hosted or disclosed in a public code repository and that TradingView gets free, unlimited access to verify the implementation.
- Therefore: private or self-hosted-personal deployments use Lightweight Charts and never apply. A public deployment applies in Phase 0 and signs the agreement in week 1.
- The library files live in a git-ignored folder (`ADVANCED_CHARTS_PATH`), never in the repository, the Docker image or CI. CI must build and pass with the folder absent.
- Attribution stays visible in both engines. Lightweight Charts requires the notice from its `NOTICE` file plus a link to tradingview.com on a page users see. The Advanced Charts logo and attribution are part of the licence.
- Pin versions: Lightweight Charts `^5.2`, and whatever Advanced Charts release is granted. Implement against the `datafeed-api.d.ts` that ships with that release; the published docs are versioned and the API moves between majors.
- The charting licence does not cover market data. Free-tier yfinance and Finnhub data on a public site is a separate problem (SRS §11).

## 3. Non-negotiables

These are the details that silently break a charting integration. Each one is a test in §10.

| # | Rule | Where |
| --- | --- | --- |
| 1 | Bar `time` and `nextTime` are epoch **milliseconds** UTC; `PeriodParams.from`/`to`, mark times and server time are **seconds** | adapter |
| 2 | Daily, weekly and monthly bars are stamped 00:00:00 UTC, not at the session open | backend |
| 3 | Intraday bars are aligned to the session open (09:30), not to the hour | backend |
| 4 | `getBars` returns all bars in `[from, to)`, ascending, topped up backwards to `countBack`, at least two bars when they exist | adapter + backend |
| 5 | `noData: true` only when older history is genuinely exhausted; `nextTime` is legacy | adapter |
| 6 | Resolutions are declared in `DatafeedConfiguration` **and** in each symbol, with `has_intraday` + `intraday_multipliers` and `has_daily` + `daily_multipliers` | adapter |
| 7 | `session` is exchange-local and its last time is non-inclusive; early closes go in `corrections`, holidays in `session_holidays` | adapter |
| 8 | `delayed_streaming` requires `delay` in seconds **and** the `display_data_mode` featureset; the enum is only `streaming`, `endofday`, `delayed_streaming` | adapter |
| 9 | A subscription is keyed by symbol, resolution, currency and chart type; several can be live at once and `unsubscribeBars` arrives about five seconds late | frontend |
| 10 | Only the newest bar may be pushed live, and it must be a complete OHLCV bar; history is refreshed with `resetCache()` + `chart.resetData()` | frontend |

## 4. Backend endpoints

Payloads are camelCase, per the contract rules in `AGENTS.md` §5. The adapter is the only place that speaks TradingView's snake_case. All endpoints are cached, rate-limited through the registry, and never call a provider directly.

### 4.1 `GET /api/chart/config`

```json
{
  "supportedResolutions": ["1", "5", "15", "60", "1D"],
  "exchanges": [{ "value": "INDEX", "name": "Index", "desc": "Index" }, { "value": "NASDAQ", "name": "NASDAQ", "desc": "NASDAQ" }],
  "symbolTypes": [{ "name": "All types", "value": "" }, { "name": "Index", "value": "index" }, { "name": "Stock", "value": "stock" }, { "name": "ETF", "value": "etf" }],
  "currencyCodes": ["USD"],
  "supportsSearch": true,
  "supportsMarks": false,
  "supportsTime": true
}
```

### 4.2 `GET /api/chart/symbols?query=&exchange=&type=`

Returns `SearchSymbolResultItem`-shaped rows. Search a curated universe (the five indices, ETFs, symbols seen in movers) plus a provider lookup for a ticker the user types. An empty array means no match; never invent a symbol.

```json
[{ "symbol": "^GSPC", "ticker": "^GSPC", "description": "S&P 500", "exchange": "INDEX", "type": "index" }]
```

### 4.3 `GET /api/chart/symbols/{symbol}`

Everything the adapter needs for `LibrarySymbolInfo`, including the calendar-derived session data.

```json
{
  "symbol": "^GSPC",
  "ticker": "^GSPC",
  "name": "S&P 500",
  "description": "S&P 500",
  "type": "index",
  "listedExchange": "INDEX",
  "timezone": "America/New_York",
  "session": "0930-1600",
  "subsessions": [
    { "id": "regular", "description": "Regular Trading Hours", "session": "0930-1600" },
    { "id": "extended", "description": "Extended Trading Hours", "session": "0400-2000" },
    { "id": "premarket", "description": "Pre-market", "session": "0400-0930" },
    { "id": "postmarket", "description": "Post-market", "session": "1600-2000" }
  ],
  "subsessionId": "regular",
  "sessionHolidays": "20261126,20261225,20270101",
  "corrections": "0930-1300:20261127",
  "minmov": 1,
  "pricescale": 100,
  "minmove2": 0,
  "format": "price",
  "visiblePlotsSet": "ohlc",
  "currencyCode": "USD",
  "hasIntraday": true,
  "intradayMultipliers": ["1", "5", "15", "60"],
  "hasDaily": true,
  "dailyMultipliers": ["1"],
  "supportedResolutions": ["1", "5", "15", "60", "1D"],
  "dataStatus": "delayed_streaming",
  "delay": 900,
  "isProxy": false,
  "source": "yfinance",
  "asOf": "2026-11-08T15:04:00Z"
}
```

`volume`-carrying symbols (stocks, ETFs) return `visiblePlotsSet: "ohlcv"`. ETF proxies carry `isProxy: true` and a `description` that says so, for example `"SPY (ETF proxy for S&P 500)"`.

### 4.4 `GET /api/chart/history?symbol=&resolution=&from=&to=&countBack=`

`from`/`to` arrive in **seconds**; bars leave in **milliseconds**. This is the one deliberate exception to the ISO-8601 timestamp rule in `AGENTS.md` §5: these numbers go straight into the datafeed, and converting twice is how charts end up an hour or a day off.

```json
{
  "symbol": "^GSPC",
  "resolution": "5",
  "bars": [{ "time": 1762520400000, "open": 7470.1, "high": 7477.9, "low": 7468.5, "close": 7475.46, "volume": null }],
  "noData": false,
  "source": "yfinance",
  "status": "fresh",
  "asOf": "2026-11-08T15:04:00Z"
}
```

Rules:

- Return every bar in the requested range. If the range holds fewer than `countBack` bars, walk backwards until `countBack` is met or history runs out.
- Return at least two bars whenever two exist; a single bar makes clicks on the chart throw.
- Set `noData: true` only when the request already reaches the earliest stored bar.
- On provider failure return `502` with `errors[]`-style detail and let the adapter call `onError`; the chart keeps its existing bars.
- Volume is `null` for index symbols; the adapter omits it from the bar.

### 4.5 `GET /api/chart/stream?symbols=`

Server-Sent Events with `bar` events carrying the same bar shape, plus a 15 s heartbeat. Multiplex symbols in one connection, and reuse the snapshot quote cache for the closing price. Concurrency is capped by `CHART_LIVE_SUBSCRIPTION_CAP`.

### 4.6 `GET /api/chart/time`

`{ "time": 1762520640 }` in seconds, for `getServerTime` when `supportsTime` is on.

## 5. Symbol mapping

| Dashboard symbol | Chart symbol | Source | Note |
| --- | --- | --- | --- |
| S&P 500 | `^GSPC` | yfinance only | Index levels are not on free Alpaca/Finnhub equity feeds |
| NASDAQ | `^IXIC` | yfinance only | Same |
| Dow | `^DJI` | yfinance only | Same |
| Russell 2000 | `^RUT` | yfinance only | Same |
| VIX | `^VIX` | yfinance only | `visiblePlotsSet: "c"` if only close data is available |
| Proxy fallback | `SPY`, `QQQ`, `DIA`, `IWM`, `VIXY` | Alpaca then yfinance | `isProxy: true`; never presented as the index |
| Mover row | provider ticker | Alpaca then yfinance | Type from the mover metadata |

When the snapshot carries a proxy because yfinance failed, the chart must show the proxy, not an empty index chart. The panel header repeats the proxy badge from the index card.

## 6. Sessions, holidays and early closes

- `session` is `0930-1600` in `America/New_York`. Extended hours are expressed through `subsessions` with ids `regular`, `extended`, `premarket`, `postmarket`, and `subsessionId` reflects the period currently on screen. Keep `symbolInfo.session` equal to the matching subsession's `session` value.
- Non-trading days come from `session_holidays` as `YYYYMMDD`, generated by the calendar service (SRS §9) — never a hand-maintained list.
- Early closes go in `corrections`, for example `0930-1300:20261127` (the Friday after Thanksgiving) and any other 13:00 half-day. A correction overrides a holiday for the same date.
- Bar timestamps anchor to the session open, so a 60-minute series runs 09:30, 10:30, 11:30 … Check how the provider labels its hourly bars before exposing the 60-minute resolution; if the provider's bars are hour-aligned rather than session-aligned, aggregate from 1-minute bars or keep the library's resolution rebuild enabled.
- The session and correction data also drive the market-status pop-up. Wrong sessions there look like a data bug to users, so both come from the same service as the status chip.

## 7. Live updates

- Subscription identity is symbol + resolution + currency + chart type. Two charts of the same symbol at different resolutions are two subscriptions with two `subscriberUID`s.
- Keep one upstream stream per symbol and fan out to every matching callback; do not open one SSE connection per subscription.
- Push only the newest bar, complete, with the bar time of the current period. Pushing an older bar triggers the library's `putToCacheNewBar: time violation` error.
- `unsubscribeBars` can arrive up to about five seconds after the user leaves a resolution or symbol. Keep sending until it does; the overlap is intentional.
- To replace history (a correction, a late provider fix), call `widget.activeChart().resetData()` after `resetCache()`; never rewrite a historical bar through the subscription.

## 8. Frontend structure

```
frontend/src/chart/
├── ChartPanel.tsx        host: dialog/route, error and stale states, attribution
├── useChartData.ts       fetch + cache the four endpoints (TanStack Query)
├── lightweight.ts        Lightweight Charts 5.x renderer
├── datafeed.ts           Advanced Charts IExternalDatafeed + IDatafeedChartApi
└── symbolInfo.ts         camelCase → LibrarySymbolInfo mapping (single source)
```

- Lightweight Charts 5.x uses `createChart(container)` then `chart.addSeries(AreaSeries | CandlestickSeries)`. The v4 `addLineSeries` family is gone.
- The panel is loaded with a dynamic import and only when a card or mover row is clicked.
- Resolutions come from `/api/chart/config`, not from constants in the component.
- The panel shows the feed chip (`IEX feed`, `delayed 15 min`, `end of day`) next to the symbol, sourced from `dataStatus`/`delay`.
- Loading skeleton, stale badge, error card with Retry, and an empty state for a symbol with no history. `prefers-reduced-motion` disables any entry animation.
- Attribution block: the NOTICE text and a tradingview.com link for Lightweight Charts; the TradingView logo stays visible for Advanced Charts.

Widget construction for Advanced Charts:

```ts
new TradingView.widget({
  container: el,
  library_path: `${advancedChartsPath}/charting_library/`,
  datafeed,
  symbol: '^GSPC',
  interval: '5',
  timezone: 'America/New_York',
  locale: 'en',
  theme: 'dark',
  autosize: true,
  disabled_features: ['header_saveload'],   // MPT has no accounts, so no saved layouts
  enabled_features: ['display_data_mode'],  // required for data_status/delay
});
```

## 9. Build order

| Step | Work | Est. | Done when |
| --- | --- | --- | --- |
| C0 | Pin `lightweight-charts@^5.2`, add the code-split `ChartPanel`, attribution, open from a card | 0.25 d | A card opens an empty themed panel with attribution |
| C1 | `/api/chart/config`, `/symbols`, `/symbols/{symbol}` from the registry and calendar service | 0.75 d | Symbol info matches §4.3 for all five indices plus SPY |
| C2 | `/api/chart/history` with the bars cache, ms conversion, `countBack` top-up and `noData` | 0.75 d | Unit tests in §10 pass; 5-minute and 1-day charts render |
| C3 | `/api/chart/stream` + `subscribeBars` fan-out under the subscription cap | 0.5 d | The newest bar updates without a reload; no time violations in the console |
| C4 | `datafeed.ts` for Advanced Charts behind `CHART_ENGINE`, with `enabled_features: ['display_data_mode']` | 0.75 d | Demo datafeed replaced by ours against the trial library, or the switch stays dark until access arrives |
| C5 | Error, stale, empty and reduced-motion states; Playwright coverage | 0.5 d | §10 green in CI with no live network |

Total: about 3.25 dev-days, split across Phases 1, 2 and 5 of the timeline.

## 10. Tests

| Level | Case |
| --- | --- |
| Unit | `camelCase` to `LibrarySymbolInfo` mapping, including required fields and `visiblePlotsSet` |
| Unit | seconds to milliseconds conversion; daily bars stamped 00:00:00 UTC |
| Unit | `countBack` top-up: fewer bars in range, more bars in range, empty result |
| Unit | Session and correction strings for a normal day, a holiday, and `20261127` |
| Unit | `dataStatus`/`delay` derivation from `feedDelaySeconds` and section status |
| Contract | `/api/chart/*` responses validated against their models using recorded fixtures |
| Failure injection | Provider timeout and 429 on history: adapter calls `onError`, chart keeps its bars |
| Frontend | Lightweight panel renders a fixture series; empty and error states; reduced motion |
| Playwright | Open a chart from a card, switch resolution, close and reopen, no console errors |
| Manual | Real ticker tape widget (FR-27) with CSP applied, offline mode hides it |

No test calls a provider or TradingView. Fixtures come from `scripts/record_fixtures.py`.

## 11. Quota and caching

- History requests go through the registry, so they inherit the token bucket and circuit breaker.
- Cache key: symbol, resolution, `from`, `to`. Coalesce identical in-flight requests; the library also caches history client-side, so do not pre-fetch resolutions the user has not chosen.
- Budget: chart history is an additive cost on top of the snapshot. Stay under 70% of the Alpaca allowance, record the new estimate in [provider-notes.md](./provider-notes.md), and keep `CHART_LIVE_SUBSCRIPTION_CAP` far below the 30-symbol free stream limit.
- Sparklines keep coming from the snapshot; the chart never replaces them.

## 12. Risks

| Risk | Effect | Response |
| --- | --- | --- |
| Advanced Charts access refused or delayed | None for v1 | Lightweight Charts ships; the abstraction already covers it |
| Public deployment is actually behind a login or paywall | Licence breach | Confirm the gate in Phase 0; if it is private, do not apply |
| Provider bars are hour-aligned, not session-aligned | Shifted intraday bars | Verify per resolution in C2; aggregate from 1-minute or keep resolution rebuild |
| Half-day or holiday missed in session data | Bars on non-trading days | Generated from the calendar service, asserted in tests, dated in fixtures |
| yfinance intraday depth is short | Sparse long-range intraday charts | Alpaca first for history; disclose the source |
| Someone commits the Advanced Charts files | Licence breach | Git-ignored path, CI builds without it, PR checklist item |

## 13. References

- API reference: <https://www.tradingview.com/charting-library-docs/latest/api/>
- Datafeed API and time units: <https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api>
- Required methods (`onReady`, `searchSymbols`, `resolveSymbol`, `getBars`): <https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/required-methods>
- Datafeed subscriptions: <https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/datafeed-subscriptions>
- Symbology and sessions: <https://www.tradingview.com/charting-library-docs/latest/connecting_data/Symbology>, <https://www.tradingview.com/charting-library-docs/latest/connecting_data/time-and-sessions/Trading-Sessions>
- Resolutions: <https://www.tradingview.com/charting-library-docs/latest/connecting_data/time-and-sessions/configure-datafeed-resolutions>
- Widget Constructor: <https://www.tradingview.com/charting-library-docs/latest/configuration/Widget-Constructor>
- Licensing and access: <https://www.tradingview.com/charting-library-docs/latest/introduction>, <https://www.tradingview.com/free-charting-libraries/>
- Lightweight Charts: <https://tradingview.github.io/lightweight-charts/docs>
