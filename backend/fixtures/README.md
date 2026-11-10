# Recorded provider payloads

`provider-recording.json` is the input to replay mode: `app/services/replay.py` maps it onto
the snapshot builder, so `GET /api/market` can serve a contract-valid snapshot before any
provider is wired up. Nothing here is fetched at runtime and no test calls the network
(`AGENTS.md` §8).

## Where the data comes from

The current file is a **shape fixture**: it was written by hand against the response shapes
in [`docs/provider-notes.md`](../../docs/provider-notes.md), and its numbers are illustrative,
not captured from Yahoo, Alpaca or Finnhub. `scripts/record_fixtures.py` does not exist yet;
when it lands it should overwrite this file with a real capture, keeping the same structure
and stripping keys and account identifiers (`AGENTS.md` §13).

## How it is marked

Replay is never disguised as live data (`AGENTS.md` rule 9):

- every entry in `status` is rewritten to `stale`;
- an `errors[]` entry with `section: "snapshot"` and `provider: "replay"` names the recording's
  `capturedAt`, so the UI can show the stale badge and the disclosure;
- `fetchedAt` keeps the recording time rather than the build time, so the payload cannot claim
  to be fresher than its data;
- `app_env=production` disables replay entirely: the app then boots with an empty store and
  `/api/market` answers `503` until a provider fills it.

## Shape

| Key | Section | Notes |
| --- | --- | --- |
| `sections.quotes` | `indexes` | One row per card; `provider`, `delaySeconds`, `rows`. |
| `sections.movers` | `movers` | `gainers`, `losers`, `mostActive` share one screener call, so they share provenance. |
| `sections.news` | `news` (into `sentiment.headlines`) | Up to five.
| `sections.marketStatus` | `status` | `value` is the contract enum; anything else fails loudly. |
| `sentiment` | `sentiment` | `verdict`, `position`, `summary`, `components` with effective weights. |

Rows use the contract's camelCase field names, which the generated models accept directly
(`populate_by_name`), so a recording can be pasted next to the example snapshots in
`shared/schema/examples/` without translation.
