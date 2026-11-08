# Provider notes and quota accounting

Working notes for the providers in the [SRS](./SRS.md) §4.1: what each one allows, what it costs us, and the Phase 0 spikes that still have to confirm it. `AGENTS.md` rule 10 requires this file to be updated whenever a provider call is added or changed; the PR checklist links here.

Limits move, so nothing in §2 is authoritative until the spike in §7 has dated it. Numbers written from memory are marked **unverified** and must not be quoted in a deployment plan.

## 1. Capability matrix

Mirror of SRS §4.1. Nothing else may call a provider directly (`AGENTS.md` rule 3).

| Capability | Primary | Fallback | Last resort |
| --- | --- | --- | --- |
| Index quotes | yfinance | ETF proxies on Alpaca/Finnhub (`SPY`, `QQQ`, `DIA`, `IWM`, `VIXY`) | Last-good snapshot |
| Intraday sparkline series | yfinance (5-minute history) | Alpaca bars on proxy ETFs | Cached series |
| Top gainers / losers | Alpaca screener | yfinance predefined screeners | Cached list |
| Most active | Alpaca most-actives | yfinance screeners | Cached list |
| Market status | Alpaca clock + calendar | Finnhub market-status | Bundled NYSE calendar |
| Headlines | Finnhub market news | Alpaca news | None |
| Chart bars (1/5/15/60 min, 1D) | Alpaca bars | yfinance | Cached bars marked `stale` |
| Chart symbol search / resolve | Curated list + yfinance | Alpaca | Static index symbols |

Index levels are not on the free Alpaca or Finnhub equity feeds, so `^GSPC`, `^IXIC`, `^DJI`, `^RUT` and `^VIX` are yfinance-only. When a proxy stands in, it stays labelled as a proxy (SRS §4.1, `AGENTS.md` rule 7).

## 2. Documented limits

| Provider | Plan | Rate limit | Other caps | Terms | Verified |
| --- | --- | --- | --- | --- | --- |
| yfinance | none — unofficial wrapper over Yahoo Finance endpoints | No published limit; see the politeness rule below | Can break, rate-limit or block without notice | Yahoo terms generally restrict to personal use | **unverified** |
| Alpaca | Basic (free) | about 200 historical REST calls/min | 30 WebSocket symbols; IEX real-time, SIP delayed 15 min | Personal use on the free tier | **unverified** |
| Finnhub | Free | about 60 calls/min, 30/s burst | News sentiment is premium; the candle endpoint is reported restricted on free keys | Personal, non-commercial | **unverified** |

Self-imposed rules beyond the vendor numbers:

- **yfinance**: one shared session per process, at least 15 s between calls to the same endpoint family, every response cached, exponential backoff with jitter on 429/403, and failover rather than retry storms. The daily CI canary (`canary.yml`) is the only live caller.
- **Alpaca**: never more than one in-flight request per endpoint; batch symbols into one request instead of looping.
- **Finnhub**: keep the whole application under 1 call/s so a burst never approaches the 30/s ceiling.

## 3. The 70% budget

`AGENTS.md` rule 10: stay under 70% of each documented quota.

| Provider | Documented | 70% ceiling, per minute | 70% ceiling, per hour |
| --- | --- | --- | --- |
| Alpaca | 200/min | 140/min | 8,400/h |
| Finnhub | 60/min | 42/min | 2,520/h |
| yfinance | unpublishable | — | politeness rule in §2 instead |

These ceilings are enforced by the registry's token bucket (`core/config.py`), not discovered by hitting them.

## 4. Steady-state snapshot budget

A regular session is 6.5 h; figures are calls per hour during regular hours, using the cadences in SRS §9.

| Section | Cadence | Calls/cycle | Calls/h | Provider | Notes |
| --- | --- | --- | --- | --- | --- |
| Index quotes | 15–30 s | 1 | 780–1,560 | yfinance | One batched request for all five indices |
| Sparklines | 5 min | 1 | 12 | yfinance | 5-minute history for five symbols, batched |
| Movers + most active | 60 s | 2 | 120 | Alpaca | One screener call each; the yfinance fallback also costs 2 |
| Market status | 60 s | 1 | 60 | Alpaca clock | Calendar fetched twice per day, not per cycle |
| Headlines | 5 min | 1 | 12 | Finnhub | Up to 5 headlines kept |
| Mood recompute | with quotes | 0 | 0 | — | Pure computation over existing data |

Provider totals before chart traffic:

| Provider | Calls/h | % of documented | % of 70% ceiling |
| --- | --- | --- | --- |
| Alpaca | 180 | 1.5% | 2.1% |
| Finnhub | 12 | 0.3% | 0.5% |
| yfinance | 792–1,572 | n/a | governed by the politeness rule |

Off-hours cadences are lower (SRS §9), so these are the worst regular-session figures. Movers at 60 s is the dominant Alpaca cost; dropping it to 90 s halves that line if a quota problem ever appears.

## 5. Chart history budget

The chart ([tradingview.md](./tradingview.md) §4.4) is the only on-demand consumer, so it is the one that can spike.

Assumptions, all to be re-checked in spike S-07:

- A `getBars` call returns about 300 bars (`countBack`), and the library pages backwards for older data.
- One chart open costs 3–5 history requests: the initial load, one or two pages back, and one resolution switch.
- Bars come from cache when the same symbol, resolution and range were requested recently, so re-opening the same chart is free.
- Live updates come from `/api/chart/stream`, never from history.

Bars per request, by resolution (390 regular-session minutes):

| Resolution | Bars per session | Sessions covered by 300 bars |
| --- | --- | --- |
| 1 min | 390 | 0.8 |
| 5 min | 78 | 3.8 |
| 15 min | 26 | 11.5 |
| 60 min | 6.5 | 46 |
| 1 day | 1 | 300 |

So 1-minute charts page the most and daily charts almost never do. Two consequences: coalesce identical in-flight requests, and do not pre-fetch resolutions the user has not selected.

Allocation for charts against the Alpaca 70% ceiling:

| Item | Reserve |
| --- | --- |
| Steady-state snapshot traffic | 180/h |
| Chart history ceiling | 1,500/h |
| Total | 1,680/h, about 14% of documented and 20% of the 70% ceiling |

Guards:

- A dedicated token bucket for `/api/chart/*`, so a charting bug cannot starve the snapshot.
- Identical in-flight requests are coalesced; a bars cache keyed by symbol, resolution, `from` and `to`.
- `CHART_LIVE_SUBSCRIPTION_CAP` (default 10) caps concurrent bar subscriptions, far below the 30-symbol free WebSocket limit.
- A per-client rate limit on `/api/chart/history`, and no history requests at all while the tab is hidden.

## 6. Feed type and delay disclosure

`feedDelaySeconds` and the footer text come from this table. Provisional values are placeholders until the spike confirms them.

| Provider | Feed | Real-time? | `feedDelaySeconds` | UI disclosure |
| --- | --- | --- | --- | --- |
| Alpaca, `ALPACA_FEED=iex` | IEX only | Yes, for the latest 15 min | 0 | "IEX feed — volume understates the consolidated market" |
| Alpaca, SIP | Consolidated | No, 15-min delay on the free plan | 900 | "Delayed up to 15 minutes" |
| yfinance | Yahoo endpoints | Not guaranteed | 900 (provisional) | "Data may be delayed" |
| Finnhub | US quotes | Yes on the free tier | 0 (provisional) | "Finnhub real-time quote" |

Chart `data_status` follows the same table: `streaming` for a real-time feed, `delayed_streaming` with `delay` for a delayed one, `endofday` when only a close is available ([tradingview.md](./tradingview.md) §3).

## 7. Phase 0 spike slots

Each slot is a dated experiment with a recorded answer; "open" means nobody has run it yet. Effort matches the Phase 0 table in the [timeline](./TIMELINE.md).

| ID | Question | Provider | Est. | Status |
| --- | --- | --- | --- | --- |
| S-01 | Create Alpaca (paper) and Finnhub keys; confirm what each free key can reach | Alpaca, Finnhub | 0.25 d | open |
| S-02 | Do `^GSPC`, `^IXIC`, `^DJI`, `^RUT` and `^VIX` quote and return a stable 140-point 5-minute series? How far back do 1/5/15-minute histories go? | yfinance | 0.5 d | open |
| S-03 | Which yfinance screeners still work for gainers, losers and most active, and which fields do they return? | yfinance | 0.5 d | open |
| S-04 | Are Alpaca movers, most-actives, clock, calendar and news available on the free plan? Measure the IEX-versus-SIP effect on volume | Alpaca | 0.75 d | open |
| S-05 | Which Finnhub free endpoints work — quote, market-status, market-news? Confirm the candle endpoint's status | Finnhub | 0.5 d | open |
| S-06 | How are provider bars anchored: session-aligned (09:30, 10:30 …) or hour-aligned? Needed before exposing the 60-minute resolution | Alpaca, yfinance | 0.25 d | open |
| S-07 | What `countBack` and ranges does the charting library actually request per resolution, and how often does it page on scroll? | chart harness | 0.25 d | open |
| S-08 | Where does each provider actually start rejecting? Probe with a doubling request rate and record the first 429/403 | all | 0.25 d | open |

Write results into §8 with the date, and fix the affected number in §2, §4, §5 or §6 in the same PR. A spike that changes a limit but leaves this file stale is not finished.

## 8. Verification log

| Date | Provider | Limit or behaviour | Observed | Source |
| --- | --- | --- | --- | --- |
| — | — | no entries yet | — | — |

## 9. PR quota checklist

Copy into the PR description when provider calls change:

- [ ] New or changed call listed in §4 (or §5 for chart traffic), with its cadence
- [ ] Provider total still under the 70% ceiling in §3
- [ ] Rate limiter and circuit breaker apply to the new path
- [ ] Cache key and TTL stated
- [ ] Failure-injection test added (timeout, 429, malformed JSON, empty payload)
- [ ] Fixtures recorded through `scripts/record_fixtures.py`, keys and account IDs stripped
- [ ] No test or fixture refresh runs live from CI except the daily canary
- [ ] Disclosure in §6 still accurate for the feed this call uses
