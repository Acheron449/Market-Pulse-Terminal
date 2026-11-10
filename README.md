# Market Pulse Terminal

A self-hosted, auto-updating US markets dashboard: five index cards with sparklines, a
market-mood gauge, and top gainers / losers / most active, fed by yfinance, Alpaca and
Finnhub. FastAPI backend, React + Vite frontend, JSON Schema as the single source of truth
for the snapshot contract.

The specification lives in [`docs/`](./docs): the [SRS](./docs/SRS.md) (requirement IDs),
the [timeline](./docs/TIMELINE.md), [provider notes](./docs/provider-notes.md),
[sentiment method](./docs/sentiment.md) and [chart plan](./docs/tradingview.md).
Contributor rules, including the architecture invariants, are in [`AGENTS.md`](./AGENTS.md).

## Quick start (no keys, no network)

A fresh clone serves the recorded provider payload in **replay mode**: everything renders,
every section is marked `stale`, and `errors[]` explains that the data is a recording. No
provider is contacted, because live access is opt-in.

```bash
cp .env.example .env                     # defaults are fine for this mode

cd backend && uv sync
uv run uvicorn app.main:app --port 8000  # http://127.0.0.1:8000/api/health

cd frontend && pnpm install
pnpm dev                                 # http://localhost:5173, proxies /api → :8000
```

The backend also serves `frontend/dist` when it exists, so `pnpm build` gives you the whole
app on one port at `http://127.0.0.1:8000/`.

## Live mode

1. Create an Alpaca paper account and a Finnhub free key.
2. Put them in `.env` (`ALPACA_API_KEY`, `ALPACA_API_SECRET`, `FINNHUB_API_KEY`).
3. Set `ENABLE_LIVE_DATA=true` and restart the API.

Live mode starts the scheduler, which fetches at the cadence in SRS §9 for the current
market state (regular / pre-market / after-hours / closed), through the registry's ordered
failover, token buckets and circuit breakers. Without Alpaca or Finnhub keys the app still
runs yfinance-only for indices, movers and charts; status comes from the bundled NYSE
calendar.

Replay is refused when `APP_ENV=production`, so a deployed instance can never present a
recording as live data. The fixture holds snapshot data only, so `/api/chart/history`
answers 502 in replay mode and the chart panel shows its Retry state; charts need live
providers.

## Docker

```bash
cp .env.example .env        # set keys, ENABLE_LIVE_DATA=true
docker compose up --build   # http://localhost:8000
```

One container: stage 1 builds the SPA, stage 2 runs uvicorn and serves that build on the
same origin. The SQLite last-good snapshot lives in the `mpt-data` volume, so a restart
serves the previous snapshot until the first refresh completes (FR-18).

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/market` | Schema-valid snapshot; `?refresh=1` forces a refresh subject to `REFRESH_COOLDOWN_SECONDS` (429 + `Retry-After` otherwise) |
| `GET /api/stream` | SSE: snapshot events plus a 15 s heartbeat |
| `GET /api/health` | Provider states, section statuses, mode and circuit state |
| `GET /api/config` | Non-secret UI flags (cooldown, chart engine, live mode) |
| `GET /api/chart/config`, `/api/chart/symbols`, `/api/chart/symbols/{symbol}/history`, `/time` | Chart drill-down data |

## Commands

Backend, from `backend/`:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app           # strict
uv run pytest             # unit + contract + API; no network
```

Frontend, from `frontend/`:

```bash
pnpm lint && pnpm typecheck && pnpm test && pnpm build

pnpm e2e:install     # one-time Chromium download for the suites below
pnpm e2e             # builds, then runs Playwright + axe against the real replay app
```

`pnpm e2e` is the one command a reviewer needs: it type-checks and builds the SPA, then
Playwright starts `uv run uvicorn app.main:app` on `127.0.0.1:8010` with
`ENABLE_LIVE_DATA=false`, which serves that build. No dev server, no mocks and no provider
calls are involved.

Schema contract:

```bash
./scripts/gen_types.sh              # schema → Pydantic models + TypeScript types
python scripts/validate_schema.py   # metaschema + example snapshots
```

## Layout

```
shared/schema/          market-snapshot.schema.json (source of truth)
scripts/                gen_types, validate_schema, canary
backend/app/
  api/                  market, stream, health, config, chart routes
  core/                 settings, SQLite cache, scheduler
  models/               generated snapshot models
  providers/            base, yfinance, alpaca, finnhub, calendar, registry, factory
  services/             snapshot builder, sentiment, market hours, movers, replay, chart, SSE bus
backend/tests/          unit/, contract/, API surface; fixtures only
backend/fixtures/       recorded provider payload used by replay mode
frontend/src/           components, hooks, chart, lib formatters, generated types, pages
```

## Design decisions and deviations from the SRS

- **`ENABLE_LIVE_DATA` (new, default `false`).** AGENTS.md §8 forbids live calls in tests,
  and a clone with no keys must still work, so provider access is gated rather than
  implicit. It is the only added environment variable; it is documented in `.env.example`.
- **Replay mode.** `/api/market` is built by the same pure snapshot builder from
  `backend/fixtures/provider-recording.json`. All sections are `stale` and a disclosure is
  appended to `errors[]`, so it is never presented as live.
- **Providers return contract-shaped rows.** They normalise vendor payloads; the snapshot
  builder is the single validation gate (AGENTS.md rule 6), which keeps the models
  generated and the validation logic in one place.
- **Purpose-built hooks instead of a query cache.** The snapshot uses SSE with a 30 s
  polling fallback, paused while the tab is hidden (SRS §9); chart history is a single
  on-demand fetch with explicit loading and error states. TanStack Query backs only the
  non-critical `/api/config` fetch.
- **Hand-rolled Tailwind components instead of shadcn/Radix.** The UI is small and fixed:
  cards, gauge, table, skeletons. No new UI dependency was added (AGENTS.md §7).

## Status against the timeline

Phases 0–4 of [`docs/TIMELINE.md`](./docs/TIMELINE.md) are implemented and tested
(schema + CI, MVP pipeline, multi-provider failover, auto-update engine, mood and
headlines). `docs/TIMELINE.md` §8 records the per-phase state.

The Phase 5 browser gap is closed. `frontend/e2e/` drives the served app in replay mode:

| Spec | What it pins down |
| --- | --- |
| `replay-dashboard.spec.ts` | Five index cards with price, change and sparkline; mood gauge value and verdict; after-hours status; movers rows and their volume/range tooltip; replay disclosure banner; disclaimer footer; refresh cooldown in the UI *and* the 429 from the API, plus the 429 resync path |
| `replay-chart.spec.ts` | Card and mover-row chart dialogs: open → loading → replay error with Retry → close; resolution switch refetching; graceful handling of symbols without a descriptor |
| `accessibility.spec.ts` | axe-core on the dashboard and the open chart dialog with WCAG 2.1/2.2 A/AA tags; fails on serious or critical findings |

Still open, all Phase 5/6 hardening rather than product behaviour:

- Live-data verification: the suite runs replay only, so provider behaviour, sentiment
  calibration over 20 historical days and the five-day soak still need real keys.
- Lighthouse performance pass and the Advanced Charts licence decision
  (`CHART_ENGINE=advanced` is accepted by config but only the Lightweight Charts engine
  is wired).
- Optional LLM summary (FR-12): `ENABLE_LLM_SUMMARY` exists and stays off; no key is read.
- Sentiment calibration over 20 historical days (`docs/sentiment.md` §12 notes the method
  and the open calibration).

## Disclaimer

Informational only, not investment advice. Free feeds are delayed or partial: Alpaca's
IEX feed understates consolidated volume, Yahoo data may be delayed, and index levels are
only available through yfinance. When an ETF proxy stands in for an index the card says so.
