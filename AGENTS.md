# AGENTS.md — Market Pulse Terminal

Instructions for AI coding agents (and humans) working in this repository. Read this file first, then the SRS (`docs/SRS.md`) and timeline (`docs/TIMELINE.md`). Requirement IDs (FR-x, NFR-x) in the SRS are the source of truth for scope.

## 1. Project overview

Market Pulse Terminal (MPT) is a self-hosted, auto-updating US markets dashboard: five index cards (S&P 500, NASDAQ, Dow, Russell 2000, VIX), a market-mood gauge, and top gainers / losers / most active lists. It is modelled on a Perplexity Finance reference build but fed by our own providers: **yfinance**, **Alpaca**, **Finnhub**, with TradingView used only as an optional embedded widget.

- **Backend**: Python 3.12, FastAPI, httpx, APScheduler (or asyncio tasks), SQLite, Pydantic v2.
- **Frontend**: React + Vite + TypeScript, Tailwind, shadcn/Radix, TanStack Query, wouter (hash routing).
- **Contract**: `shared/schema/market-snapshot.schema.json` is the single source of truth for the snapshot JSON.

## 2. Repository layout

```
.
├── AGENTS.md
├── docs/                      SRS.md, TIMELINE.md, provider-notes.md, tradingview.md, sentiment.md
├── shared/schema/             market-snapshot.schema.json (source of truth)
├── backend/
│   ├── app/
│   │   ├── api/               FastAPI routes: /api/market, /api/stream, /api/health, /api/config
│   │   ├── core/              config, logging, cache, scheduler, rate limiter, circuit breaker
│   │   ├── models/            Pydantic models generated or validated from the schema
│   │   ├── providers/         base.py, yfinance_provider.py, alpaca_provider.py, finnhub_provider.py, registry.py
│   │   └── services/          snapshot_builder.py, sentiment.py, market_hours.py, movers_filter.py
│   ├── tests/                 unit/, contract/, failure_injection/
│   └── tests/fixtures/        recorded provider responses (no live calls in tests)
├── frontend/
│   └── src/                   components/, hooks/, lib/ (formatters), types/ (generated), pages/
├── scripts/                   export_static_snapshot.py, record_fixtures.py, gen_types.sh, validate_schema.py
├── docker-compose.yml
└── .github/workflows/         ci.yml, canary.yml
```

## 3. Setup and commands

Backend (uses `uv`):

```bash
cd backend
uv sync
cp ../.env.example ../.env          # then add keys; never commit .env
uv run uvicorn app.main:app --reload --port 8000
uv run pytest -q                    # unit + contract + failure-injection
uv run ruff check . && uv run ruff format --check .
uv run mypy app
```

Frontend (uses `pnpm`):

```bash
cd frontend
pnpm install
pnpm dev                            # Vite on :5173, proxies /api to :8000
pnpm test                           # Vitest
pnpm lint && pnpm typecheck
pnpm e2e                            # Playwright (uses recorded fixtures, replay mode)
```

Schema and types:

```bash
./scripts/gen_types.sh              # regenerates backend models and frontend types from the JSON schema
python scripts/validate_schema.py   # validates the schema and the example snapshots (also runs in CI)
```

Everything in one go: `docker compose up --build`.

## 4. Architecture rules (do not break these)

1. **Only the backend talks to data providers.** The browser never calls yfinance, Alpaca, Finnhub or any market API directly.
2. **API keys never reach the browser, logs, error messages, fixtures or the built frontend.** Redact on log. Use environment variables only.
3. **All provider access goes through the registry** (`providers/registry.py`), which applies capability routing, ordered failover, per-provider token-bucket rate limits and a circuit breaker. Never call a provider client directly from a route or service.
4. **Providers implement `MarketDataProvider`** (`providers/base.py`) and declare supported capabilities: `quotes`, `series`, `movers`, `status`, `news`. Return normalized internal models, not raw vendor payloads.
5. **Every snapshot section has its own `status` (`fresh | stale | error`), `source` and `asOf`.** A failed refresh keeps the last good data and marks it stale; it must never blank a section.
6. **Validate all provider data** before it enters the snapshot: finite numbers, price > 0, non-empty symbol, plausible percent change. Drop or flag bad rows and record an entry in `errors[]`.
7. **Index levels versus ETF proxies**: free Alpaca/Finnhub equity feeds do not provide index levels. If a proxy ETF (SPY, QQQ, DIA, IWM, VIXY) substitutes for an index, set `isProxy: true` and show it as the ETF. Never present a proxy price as the index value.
8. **TradingView is UI-only.** Do not scrape TradingView or add an unofficial TradingView data client. Use only its official embeddable widgets, with attribution, behind a feature flag.
9. **Never fabricate or hard-code market data** in production paths. Sample data lives in `tests/fixtures/` and `frontend/public/market-data.sample.json` and is used only in tests, replay mode, or when explicitly flagged as a demo.
10. **Respect provider limits.** Stay under 70% of each documented quota. When adding a call, update the quota estimate in `docs/provider-notes.md`. Limits change, so verify them against the vendor docs rather than relying on memory or this file.

## 5. Data contract rules

- Change the JSON schema **first**, then regenerate types, then update backend and frontend. Never hand-edit generated files.
- Additive changes (new optional fields) are allowed within `schemaVersion: 1`. Removing or renaming a field requires a version bump, a migration note in `docs/`, and an update to the static-export fallback.
- Keep the reference-compatible fields intact: `indexes[]` (`symbol`, `label`, `price`, `change`, `changePercent`, `invert`, `sparkline`), `sentiment` (`verdict`, `position`, `marketStatus`, `summary`, `headlines`, `components`), `gainers[]`, `losers[]`, `mostActive[]` (`volume`, `dayLow`, `dayHigh`), `fetchedAt`, `errors[]`.
- `sentiment.verdict` is one of `BEARISH | UNCERTAIN | NEUTRAL | BULLISH | UNKNOWN`. `position` is 0–100. `marketStatus` is one of `pre_market | regular | after_hours | closed | unknown`.
- Timestamps are UTC ISO-8601. Convert to the user's locale only in the frontend.

## 6. Auto-update behaviour

- Cadences per section and market state are defined in SRS section 9 and configured in `core/config.py`. Do not hard-code intervals in providers or components.
- The scheduler must add jitter, skip a cycle if the previous one is still running, and back off exponentially on failure.
- Market state comes from the Alpaca clock/calendar, then Finnhub market-status, then the bundled NYSE calendar. Treat holidays and early closes as first-class cases.
- The frontend uses SSE (`/api/stream`) with a 30-second polling fallback and pauses polling while the tab is hidden. `?refresh=1` is subject to the cooldown (default 10 s).

## 7. Frontend conventions

- Match the reference layout and behaviour in SRS section 1.3 and 7.2: max width 1320 px, dark theme default, monospace tabular numerals for all figures.
- Palette tokens: up `#00E676`, down `#FF5252`, caution `#F0B429`, volume `#22D3EE`. Honour `invert` for VIX (rising VIX is red).
- Colour is never the only signal: keep `+/-` signs and arrows. Respect `prefers-reduced-motion`.
- Formatters live in `src/lib/format.ts`: two decimals, signed changes, K/M/B volume, `—` for invalid values, symbol names truncated for display. Reuse them; do not reimplement inline.
- Include loading skeletons, an empty-state, an error card with Retry, a stale badge and the "some sections couldn't load" banner.
- Load at most two font families. Do not copy the reference's long font list.
- Do not introduce new UI libraries without noting why in the PR.

## 8. Testing rules

- **No live network calls in tests.** Use recorded fixtures (`scripts/record_fixtures.py` refreshes them manually; fixtures must have keys and account IDs stripped).
- New provider code needs: a contract test mapping fixtures into the snapshot, and failure-injection tests (timeout, 429, malformed JSON, empty list, stale timestamp).
- Sentiment functions are pure and need table-driven tests, including the case where components are missing and weights are redistributed.
- Every API response in tests is validated against the JSON schema.
- Backend coverage target is 80% on `core/`, `providers/` and `services/`.
- Frontend changes that alter visible behaviour need a component test; flows (load, live update, stale, error, refresh cooldown) are covered in Playwright.
- A CI canary job (`canary.yml`) runs a daily live smoke test of yfinance; a failure there is a signal to check provider changes, not to relax tests.

## 9. Code style

- Python: type hints everywhere, `ruff` for lint and format, `mypy --strict` on `app/`. Async by default for I/O. Pydantic models for all boundary data. No bare `except`.
- TypeScript: `strict` mode, no `any` without a comment, functional components and hooks.
- Names: `snake_case` in Python, `camelCase` in the JSON contract and TypeScript.
- Small modules, small functions. Prefer pure functions in `services/`.
- Comments explain why, not what. Link the SRS requirement ID where it helps (for example `# FR-9: retain last-good section`).

## 10. Git and PR workflow

- Branches: `feat/<short-name>`, `fix/<short-name>`, `chore/<short-name>`.
- Commits follow Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
- One logical change per PR, ideally under 400 changed lines. Reference the SRS IDs it satisfies.
- PR checklist (copy into the description):
  - [ ] Tests added or updated and passing locally
  - [ ] `ruff`, `mypy`, `eslint`, `tsc` clean
  - [ ] Schema, generated types and fixtures in sync
  - [ ] No secrets, no live-network tests, no hard-coded market data
  - [ ] Quota impact noted in `docs/provider-notes.md` if provider calls changed
  - [ ] Docs updated (`SRS`, `TIMELINE` or `provider-notes`) if behaviour changed
  - [ ] Screenshots attached for UI changes

## 11. Task playbooks

### Add a new data provider
1. Write a spike note in `docs/provider-notes.md`: capabilities, free-tier limits, terms of use, delay and feed type.
2. Create `providers/<name>_provider.py` implementing `MarketDataProvider`; declare only the capabilities it genuinely supports.
3. Register it in `registry.py` and expose its position in the `PROVIDER_ORDER_*` settings.
4. Add recorded fixtures, contract tests and failure-injection tests.
5. Confirm `/api/health` reports its state and that quota metrics are emitted.

### Add a new dashboard widget
1. Add the data to the JSON schema as optional fields; regenerate types.
2. Extend `snapshot_builder.py` with per-section status, source and `asOf`.
3. Choose a refresh cadence and add it to the scheduler config.
4. Build the component with skeleton, stale and error states, then add tests.
5. Update SRS section 5 with a new FR entry.

### Change the market-mood calculation
1. Edit `services/sentiment.py` and `docs/sentiment.md` together.
2. Keep weights and verdict bands configurable; keep the `components` array exposed.
3. Add table-driven tests with at least one case per verdict band and one with missing components.
4. Do not present the output as advice; keep the disclaimer in the UI.

### Debug "data looks wrong"
1. Check `/api/health` for open circuits and stale sections.
2. Compare the snapshot's `sources` with the expected provider; look for failover.
3. Reproduce with a recorded fixture before changing logic.
4. Remember free feeds: Alpaca free is IEX-only for the latest 15 minutes (so volume and movers can differ from consolidated data), and Yahoo data may be delayed.

## 12. Compliance reminders

- The UI footer must say the data is informational only and not investment advice, and disclose feed type and possible delay (`feedDelaySeconds`, provider list).
- Free tiers are generally for personal, non-commercial use. Do not add features that redistribute raw provider data publicly. Flag any deployment plan that changes this.
- Do not copy Perplexity branding, copy or assets; the reference is a behavioural and layout guide only.

## 13. Boundaries for agents

**Always**
- Read the relevant SRS sections before starting; cite requirement IDs in commits.
- Run lint, type checks and tests before declaring work finished.
- Keep changes scoped to the task and mention anything you noticed but did not change.

**Ask first**
- Adding a dependency, provider, paid service or new environment variable.
- Changing the schema in a non-additive way, scheduler cadences, or default provider order.
- Anything that increases provider call volume noticeably.

**Never**
- Commit secrets, `.env`, real account IDs or unredacted fixtures.
- Call live providers from tests, or hard-code prices, tickers' values or "sample" data in production code.
- Scrape sites whose terms forbid it (including TradingView data endpoints).
- Bypass the provider registry, rate limiter or validators.
- Remove disclaimers, delay disclosures or proxy labels.
- Rewrite generated files by hand or disable CI checks to get a green build.

## 14. Definition of done

A task is done when: it satisfies the cited requirement IDs; tests (unit, contract and, if relevant, e2e) pass; lint and type checks are clean; schema, types and fixtures agree; the UI shows correct loading, stale and error states; docs are updated; and the PR checklist in section 10 is complete.
