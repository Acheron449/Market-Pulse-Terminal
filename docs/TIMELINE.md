# Market Pulse Terminal — Project Timeline

Version 1.0 (Draft) · 8 November 2026 · Companion to the [Market Pulse Terminal SRS](./SRS.md)

## 1. Planning Assumptions

- **Team**: one full-stack developer working with AI coding agents (guided by `AGENTS.md`). With two developers, the plan compresses to about 5 weeks by running backend and frontend tracks in parallel from Phase 1.
- **Start**: Monday 9 November 2026. **Target v1.0 release**: Wednesday 23 December 2026, with a contingency week after.
- **Effort**: about 8 calendar weeks, roughly 35 working days of effort including a 20% buffer.
- **Data**: free-tier providers only; keys for Alpaca and Finnhub are created in week 1.
- **US market calendar impacts**: markets are closed Thursday 26 November (Thanksgiving) and close early on Friday 27 November; closed Friday 25 December and Friday 1 January. These days are used deliberately to test closed and early-close behaviour.
- The reference build is compiled, so the UI is rebuilt from the behaviour captured in SRS section 1.3. No time is allotted to decompiling it.

## 2. Timeline at a Glance

| Week | Dates | Phase | Milestone at end of week |
| --- | --- | --- | --- |
| 1 | 9–13 Nov | 0. Discovery and spikes | M0: provider matrix verified, repo scaffolded |
| 2 | 16–20 Nov | 1. MVP pipeline and UI | M1: end-to-end demo from yfinance only |
| 3 | 23–27 Nov | 2. Multi-provider and failover | M2: Alpaca and Finnhub live with failover |
| 4 | 30 Nov–4 Dec | 3. Auto-update engine | M3: market-hours scheduler, SSE and stale handling |
| 5 | 7–11 Dec | 4. Market mood and headlines | M4: feature-complete beta |
| 6 | 14–18 Dec | 5. Hardening and quality | M5: release candidate; staging soak begins |
| 7 | 21–25 Dec | 6. Deploy and release | M6: v1.0 live (target 23 Dec) |
| 8 | 28 Dec–1 Jan | Contingency | Buffer for slips, soak fixes, docs |

### Week-by-track view

| Track | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Backend providers | ■ | ■ | ■ |  |  |  |  |  |
| Scheduler, cache, streaming |  | □ | □ | ■ |  |  |  |  |
| Sentiment engine |  |  |  | □ | ■ |  |  |  |
| Frontend UI | □ | ■ | □ | ■ | ■ | □ |  |  |
| Testing and hardening | □ | □ | □ | □ | □ | ■ | □ |  |
| Deployment and docs | □ |  |  |  |  | □ | ■ | □ |
| Contingency |  |  |  |  |  |  |  | ■ |

■ primary focus · □ supporting work

## 3. Phase Details

### Phase 0 — Discovery and spikes (Week 1, 9–13 Nov)

**Goal**: remove the biggest unknowns before committing to the design.

| Task | Est. | Output |
| --- | --- | --- |
| Create Alpaca (paper account) and Finnhub keys; store in a secrets file | 0.25 d | `.env.example`, key setup notes |
| Spike: yfinance for ^GSPC, ^IXIC, ^DJI, ^RUT, ^VIX quotes and 5-minute history; confirm a stable 140-point series | 0.5 d | Working notebook, sample fixtures |
| Spike: yfinance screeners for gainers, losers and most active | 0.5 d | Findings on reliability and fields |
| Spike: Alpaca movers, most-actives, clock, calendar and news on the free plan; note IEX versus SIP effects | 0.75 d | [provider-notes.md](./provider-notes.md) |
| Spike: Finnhub quote, market-status and market-news; confirm which endpoints the free key allows | 0.5 d | Same notes file |
| Freeze JSON schema v1 from the reference `market-data.json` plus new fields | 0.5 d | `shared/schema/market-snapshot.schema.json` |
| Scaffold monorepo, CI (lint, type check, tests), pre-commit, Docker skeleton | 1 d | Green CI on an empty app |
| Capture UI reference screenshots and design tokens | 0.25 d | `docs/ui-reference/` |
| Charting gate: confirm the deployment is public and free to access, apply for Advanced Charts, pin Lightweight Charts 5.x, agree [tradingview.md](./tradingview.md) | 0.25 d | Licence decision recorded; chart plan agreed |

**Exit criteria**: capability matrix confirmed (which provider serves which section on free tiers); schema frozen; CI green. **Decision gate**: if the Alpaca free screener is unavailable, movers primary becomes yfinance with Alpaca as the volume cross-check.

### Phase 1 — MVP pipeline and UI (Week 2, 16–20 Nov)

**Goal**: a working dashboard from a single provider.

| Task | Est. | Output |
| --- | --- | --- |
| Provider interface, models, validators | 1 d | `providers/base.py`, unit tests |
| yfinance provider (indices, series, movers) | 1 d | Fixture-based tests |
| Snapshot builder with last-good retention | 0.75 d | Snapshot matches schema |
| FastAPI `/api/market`, `/api/health`, static `market-data.json` export | 0.5 d | Running API |
| Frontend scaffold (Vite, React, Tailwind, shadcn, TanStack Query) and design tokens | 0.5 d | Themed shell |
| Index cards with sparklines, header, footer, skeleton and error states | 1 d | Matches reference |
| Mover columns with tooltips and bars; number formatters | 1 d | Matches reference |
| Chart drill-down: Lightweight Charts 5.x panel, `/api/chart/config`, `/symbols` and `/history`, code-split with attribution | 1 d | Chart opens from a card or mover row |

**Exit (M1)**: opening the app shows live-ish data from yfinance; killing the network shows the cached snapshot; schema validation passes in CI; clicking a card or mover row opens its chart.

### Phase 2 — Multi-provider and failover (Week 3, 23–27 Nov)

Thanksgiving week: the market is closed on Thursday, so use it to test closed-market states, and plan lighter days.

| Task | Est. | Output |
| --- | --- | --- |
| Alpaca provider (quotes, movers, most-actives, clock, news) | 1 d | Tested adapter |
| Finnhub provider (quote, market-status, news) | 0.75 d | Tested adapter |
| ETF-proxy fallback for indices, flagged `isProxy` | 0.5 d | UI badge on proxy cards |
| Chart symbol mapping: sessions, holidays and early-close corrections from the calendar service, proxy descriptions | 0.25 d | Bars land on the right timestamps on 26–27 Nov |
| Registry with ordered failover, token-bucket limiter, circuit breaker | 1 d | Failure-injection tests |
| Movers filters (price, volume, warrants, leveraged ETFs) | 0.5 d | Config-driven |
| Provider status in `/api/health` | 0.25 d | Health endpoint |

**Exit (M2)**: with any one provider disabled, every section is still populated; quota usage metrics are visible.

### Phase 3 — Auto-update engine (Week 4, 30 Nov–4 Dec)

| Task | Est. | Output |
| --- | --- | --- |
| Market-hours service (calendar, holidays, early closes) | 0.75 d | Unit tests for edge days |
| Scheduler with per-section cadence, jitter, overlap guard, backoff | 1 d | Matches SRS section 9 |
| SQLite persistence and cold-start serve of last-good snapshot | 0.5 d | Restart test |
| SSE `/api/stream` with heartbeat; polling fallback; pause on hidden tab | 1 d | Live updates without reload |
| Frontend: price flash, needle animation, live dot states, stale badges | 1 d | Reduced-motion respected |
| Manual refresh cooldown and rate limiting | 0.25 d | 429 handling in UI |

**Exit (M3)**: during a trading session the UI updates on its own at the target cadence; pre-market, after-hours and closed states change cadence and status chip correctly.

### Phase 4 — Market mood and headlines (Week 5, 7–11 Dec)

| Task | Est. | Output |
| --- | --- | --- |
| Sentiment components (volatility, trend, momentum, risk appetite) | 1 d | Pure functions with tests |
| Historical context fetch (1-year VIX percentile, 50-day average) cached daily | 0.5 d | Daily job |
| Headline ingestion, de-duplication, optional lexicon tone score | 0.75 d | Up to 5 headlines |
| Mood panel UI: gauge, verdict, components explainer, headlines list | 1 d | Matches reference |
| Optional LLM summary with cap and template fallback | 0.75 d | Feature-flagged |
| Calibration review across at least 20 historical days | 0.5 d | Notes in [sentiment.md](./sentiment.md) |

**Exit (M4)**: feature-complete beta behind a staging URL; every SRS "Must" and "Should" requirement implemented.

### Phase 5 — Hardening and quality (Week 6, 14–18 Dec)

| Task | Est. | Output |
| --- | --- | --- |
| Playwright end-to-end suite and failure-injection tests | 1 d | CI-gated |
| Accessibility pass (keyboard, ARIA, contrast, non-colour cues) | 0.75 d | Lighthouse 95+ |
| Performance and bundle-size pass; font subset (the reference loads dozens of font families, so trim to two) | 0.5 d | Budget met |
| Advanced Charts decision gate: licence signed and deployment confirmed public, or ship Lightweight Charts; switch by `CHART_ENGINE` | 0.25 d | Decision recorded; no unlicensed files in the image |
| Security review: secret scan, CORS, dependency audit, log redaction | 0.5 d | Checklist signed off |
| Metrics, structured logs, alerts for stale data and open circuits | 0.75 d | Dashboard |
| Staging deployment and start of 5-trading-day soak test | 0.5 d | Soak running |
| README, runbook, provider-limits guide | 0.5 d | `docs/` |

**Exit (M5)**: release candidate tagged; soak test running with no unresolved Sev-1 or Sev-2 defects.

### Phase 6 — Deploy and release (Week 7, 21–25 Dec)

| Task | Est. | Output |
| --- | --- | --- |
| Review soak results; fix issues found | 1 d | Fix list closed |
| Production deployment (Docker Compose or static-export mode), TLS, secrets | 0.75 d | Live URL |
| Smoke test across pre-market, regular and after-hours | 0.5 d | Signed-off checklist |
| Release notes, disclaimer and data-delay copy review | 0.25 d | v1.0 tag |

**Exit (M6)**: all acceptance criteria in SRS section 12.2 met. Friday 25 December is a market holiday and a deliberate closed-market check.

## 4. Critical Path and Dependencies

1. Provider spikes → frozen schema → everything else.
2. Registry and failover (Phase 2) → scheduler (Phase 3) → soak test (Phase 5).
3. Sentiment (Phase 4) depends on index history from Phase 1 and the scheduler from Phase 3.
4. The soak test needs five real trading days, so it cannot be compressed. Starting it on 14 December is what protects the 23 December date.

## 5. Schedule Risks

| Risk | Effect on plan | Response |
| --- | --- | --- |
| yfinance changes or blocks requests mid-project | +2–3 days in Phase 1 or 2 | Pin versions; contingency week; lean on Alpaca and Finnhub proxies |
| Free Alpaca screener unavailable or limited | +1 day | Fallback to yfinance screeners decided at the Phase 0 gate |
| Holiday weeks reduce live-market testing time | Soak overlaps Christmas | Begin soak 14 December; use recorded fixtures and replay mode for off-hours testing |
| Scope creep (watchlists, heatmaps, crypto) | Delays release | Park in the post-v1 backlog below |
| Sentiment calibration debates | +1 day | Ship configurable weights; revisit after launch |
| Advanced Charts access refused or delayed | None for v1 | Off the critical path: Lightweight Charts ships, and `ChartPanel` already abstracts the engine |

## 6. Post-v1 Backlog (not scheduled)

Watchlists and symbol search, sector heatmap, economic calendar, price alerts, crypto and futures cards, WebSocket-driven tick updates, user-selectable indices, installable PWA, paid-data provider adapter for commercial hosting.

## 7. Weekly Operating Rhythm

- **Monday**: confirm the week's scope and open risks; update this timeline if a milestone moves.
- **Daily**: merge small PRs behind green CI; agents work from `AGENTS.md` and the SRS requirement IDs.
- **Friday**: demo the milestone against its exit criteria, record provider quota usage, and decide go or slip.
