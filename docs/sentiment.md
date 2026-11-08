# Market mood: methodology and calibration

Companion to SRS §10 (market-mood methodology) and FR-10. Implements the contract fields `sentiment.verdict`, `sentiment.position` and `sentiment.components` from `shared/schema/market-snapshot.schema.json`.

The mood is a transparent composite of public data. It is a heuristic summary, not a prediction and not investment advice, and the UI must say so wherever the gauge appears (SRS §10, §11).

## 1. Shape of the calculation

Pure functions in `backend/app/services/sentiment.py`: numbers in, numbers out, no I/O, no clock reads, no randomness. `asOf` is passed in, never looked up, so replays are reproducible.

```
component score (0–100, 0 = very bearish, 100 = very bullish)
        ↓  default weight
position = Σ(weightᵢ × scoreᵢ) / Σ(weightᵢ over available components)
        ↓  rounded half-up, clamped 0–100
verdict  = band containing position   (UNKNOWN if fewer than 3 components)
```

Weights renormalise automatically, so a missing or disabled component redistributes its weight instead of dragging the score toward 50.

## 2. Inputs

| Input | Source | Refresh | Notes |
| --- | --- | --- | --- |
| VIX level and 1-year percentile | yfinance `^VIX` daily history | Cached daily after the close | Percentile over the trailing 252 trading days |
| VIX change, percent | Snapshot `indexes[]` entry for `^VIX` | With quotes (SRS §9) | Uses the same session change the card shows |
| S&P 500 level and 50-day SMA | yfinance `^GSPC` daily history | Cached daily after the close | SMA over the last 50 trading closes |
| Percent change of the four equity indices | Snapshot `indexes[]` (`^GSPC`, `^IXIC`, `^DJI`, `^RUT`) | With quotes | VIX is excluded from momentum |
| Headlines | Snapshot `sentiment.headlines` (Finnhub) | 5 min | Up to 5; de-duplicated by title and URL |
| `asOf` | Snapshot `fetchedAt` | Per snapshot | Stored with the score for replay |

Historical context (percentile and SMA) is fetched once per trading day by the scheduler; it is not a per-cycle call (see [provider-notes.md](./provider-notes.md) §4).

## 3. Components

Default weights are SRS §10. Scores are computed as floats and rounded half-up to integers when exposed.

| Component | Weight | Formula | Bounds |
| --- | --- | --- | --- |
| `volatility` | 0.30 | `0.7 × (100 − vixPercentile) + 0.3 × (50 − clamp(vixChangePercent × 10, −50, 50))` | 0–100 |
| `trend` | 0.25 | `clamp(50 + 10 × spxDistanceFromSmaPercent, 0, 100)` | 0–100 |
| `momentum` | 0.20 | `clamp(50 + 20 × meanChangePercent, 0, 100)` over the four equity indices | 0–100 |
| `riskAppetite` | 0.15 | `clamp(50 + 40 × (russellChangePercent − spxChangePercent), 0, 100)` | 0–100 |
| `headlineTone` | 0.10 | `clamp(50 + 50 × meanTone, 0, 100)`, `meanTone` in −1…+1 | 0–100 |

Notes that matter for tests:

- **Volatility is inverted twice over.** A high VIX percentile is bearish, and a rising VIX today is bearish. A +2% VIX day scores 30 on the change half; a −5% day scores 100.
- **Trend saturates at ±5%.** Ten points per percent away from the 50-day SMA: +5% → 100, −5% → 0.
- **Momentum saturates at ±2.5%.** Twenty points per percent of average change.
- **Risk appetite saturates at ±1.25 pp.** Small caps outperforming the S&P is bullish; underperforming is bearish.
- **`headlineTone` is optional.** It comes from a fixed keyword lexicon (no external model, no network), scoring each headline −1…+1, then averaged. Disabled, or with no headlines, the weight redistributes to the other four.
- **Component `weight` in the contract is the effective weight after renormalisation**, so the exposed components always sum to 1.0. The UI explainer depends on that.

## 4. Verdict bands

Bands apply to the integer `position` and are contiguous, so every result lands somewhere:

| Position | Verdict |
| --- | --- |
| 0–25 | `BEARISH` |
| 26–44 | `UNCERTAIN` |
| 45–60 | `NEUTRAL` |
| 61–100 | `BULLISH` |
| fewer than 3 components | `UNKNOWN` |

- `UNKNOWN` also occurs when no component can be computed; `position` is then `50`.
- With 1–2 components available the `position` is still the renormalised weighted score, because hiding it loses information, but the verdict is `UNKNOWN` and the UI **must not** present a direction: show the UNKNOWN label, list the components that did exist, and drop the needle's directional colour.
- `marketStatus` comes from the snapshot, not from the mood. A closed market does not change the verdict.

## 5. Worked examples

These are the fixtures the unit tests assert. Arithmetic is reproduced by `services/sentiment.py` tests, not by hand.

**A. All five components, NEUTRAL.** VIX percentile 40, VIX +2.0%, S&P +1.2% above its SMA, changes +0.45 / +0.62 / +0.31 / +0.28 (mean 0.415%), Russell − S&P −0.17 pp, mean headline tone +0.10.

| Component | Score | Weight | Contribution |
| --- | --- | --- | --- |
| `volatility` | 0.7 × 60 + 0.3 × 30 = 51 | 0.30 | 15.30 |
| `trend` | 50 + 12 = 62 | 0.25 | 15.50 |
| `momentum` | 50 + 8.3 = 58.3 | 0.20 | 11.66 |
| `riskAppetite` | 50 − 6.8 = 43.2 | 0.15 | 6.48 |
| `headlineTone` | 55 | 0.10 | 5.50 |

Position 54.44 → **54 → NEUTRAL**.

**B. Headline tone disabled, BEARISH.** VIX percentile 85, VIX +6.0%, S&P −2.1% below its SMA, changes −1.10 / −1.45 / −0.95 / −1.30 (mean −1.20%), Russell − S&P −0.20 pp.

Effective weights after renormalising over 0.90: 0.3333 / 0.2778 / 0.2222 / 0.1667, with scores 10.5 / 29 / 26 / 42.

Position 24.33 → **24 → BEARISH**.

**C. Two components, UNKNOWN.** Only `volatility` (score 40) and `trend` (score 70) are available: (0.30 × 40 + 0.25 × 70) / 0.55 = 53.64 → **54**, verdict **UNKNOWN** (fewer than three components), and the UI shows no direction.

## 6. Missing, stale and invalid data

| Case | Behaviour |
| --- | --- |
| Component inputs missing (no VIX history, no SMA yet) | Drop the component, renormalise over the rest, list only computed components |
| `headlineTone` disabled or no headlines | Drop it; the other four renormalise to 1.0 |
| 1–2 components available | `UNKNOWN` verdict, position still computed |
| 0 components available | `UNKNOWN`, position `50`, empty `components` |
| Input older than its freshness budget | Still used; the section shows its stale badge (SRS §5). Staleness does not change the verdict rule |
| Non-finite or out-of-range input | Treated as missing (`AGENTS.md` rule 6) — never substituted with a guess |
| Proxy index in place of `^GSPC` or `^VIX` | Allowed for momentum only; trend and volatility need real index history, so they drop out and the weight redistributes |

## 7. Snapshot output

```json
"sentiment": {
  "verdict": "NEUTRAL",
  "position": 54,
  "marketStatus": "regular",
  "summary": "",
  "headlines": [],
  "components": [
    { "name": "volatility", "score": 51, "weight": 0.3 },
    { "name": "trend", "score": 62, "weight": 0.25 },
    { "name": "momentum", "score": 58, "weight": 0.2 },
    { "name": "riskAppetite", "score": 43, "weight": 0.15 },
    { "name": "headlineTone", "score": 55, "weight": 0.1 }
  ]
}
```

Component names are camelCase per `AGENTS.md` §5, and the SRS §6 sample now carries the same five names, scores and weights. The JSON Schema file (`shared/schema/market-snapshot.schema.json`) is the source of truth but does not exist in this repository yet: when it is created it must define these five component names schema-first, with backend models and frontend types generated from it (`AGENTS.md` §5).

## 8. Configuration

Weights, bands and thresholds live in `core/config.py`; nothing is hard-coded in `services/` or in components (`AGENTS.md` §6).

| Setting | Default | Purpose |
| --- | --- | --- |
| `SENTIMENT_WEIGHTS` | `volatility=0.30,trend=0.25,momentum=0.20,risk_appetite=0.15,headline_tone=0.10` | Component weights; need not sum to 1 |
| `SENTIMENT_BANDS` | `bearish=25,uncertain=44,neutral=60` | Upper bounds, inclusive |
| `SENTIMENT_MIN_COMPONENTS` | `3` | Below this, verdict is `UNKNOWN` |
| `ENABLE_HEADLINE_TONE` | `true` | Turns the lexicon component on or off; off redistributes its weight |
| `ENABLE_LLM_SUMMARY` | `false` | FR-12 summary, separate from the score |

All four are listed in SRS Appendix A, alongside the existing `ENABLE_LLM_SUMMARY`.

## 9. Optional LLM summary (FR-12)

Off by default and never part of the score.

- Input is the computed numbers only (position, verdict, component scores, the day's index changes) — never raw provider payloads.
- 1–2 sentences, no advice, no price targets, no predictions; the prompt states that it summarises a heuristic.
- Cached per snapshot, so one call per snapshot at most; hard daily call cap in config.
- Any failure, timeout or missing key falls back to the deterministic template: "\<VERDICT> mood. S&P 500 \<change>%, VIX \<change>%. Based on \<n> of 5 signals."
- The UI labels it as generated and keeps the "not investment advice" line.

## 10. Tests

`AGENTS.md` §11 requires table-driven cases, one per verdict band, plus missing components. `AGENTS.md` §8 forbids live calls: every case is a plain fixture.

| Case | Expectation |
| --- | --- |
| Example A | position 54, `NEUTRAL`, five components summing to weight 1.0 |
| Example B | position 24, `BEARISH`, four components renormalised |
| Example C | position 54, `UNKNOWN` with 2 components |
| Band boundaries | 25 → `BEARISH`, 26 → `UNCERTAIN`, 44 → `UNCERTAIN`, 45 → `NEUTRAL`, 60 → `NEUTRAL`, 61 → `BULLISH` |
| `UNCERTAIN` and `BULLISH` fixtures | At least one full-component case per band |
| VIX inversion | Rising VIX lowers the score; falling VIX raises it |
| Saturation | Trend at ±5%, momentum at ±2.5%, risk appetite at ±1.25 pp, each clamped |
| All missing | `UNKNOWN`, position 50, empty `components` |
| Non-finite input | Treated as missing, no exception, no NaN in the output |
| Determinism | Same inputs and `asOf` produce an identical snapshot |
| Renormalisation | Dropping any single component leaves weights summing to 1.0 |

## 11. Calibration plan

Phase 4 closes with a review; the timeline budgets half a day for it.

**Procedure**

1. Pick 20 historical trading days that include at least one down day over 1%, one up day over 1%, and one quiet day.
2. Replay recorded daily VIX and index closes through the pure functions in replay mode — no live calls.
3. Record position, verdict, the components that fired, and the next session's S&P change.
4. Check reachability: all five verdicts appear somewhere in the window, and no single verdict covers more than 70% of days.
5. Check stability: day-over-day position moves stay under 25 points unless an index moved more than 1.5%.
6. Check coherence: no `BEARISH` verdict on a day the S&P rose more than 2%, and no `BULLISH` on a day it fell more than 2%, or the case is explained in the log.
7. Re-run after any weight or formula change and log it below.

**What this is not.** It is not a backtest and must not be described as one. The next-day direction column is a coherence check on the arithmetic, not a performance claim, and the weights are not tuned to improve it. Ship configurable weights and revisit after launch (timeline risk register).

| Run | Date | Window | Weights | Result | Notes |
| --- | --- | --- | --- | --- | --- |
| — | — | — | defaults | not run | Phase 4 |

## 12. Change log

| Date | Change | Reason |
| --- | --- | --- |
| 8 Nov 2026 | Initial methodology, weights and bands from SRS §10 | Phase 4 planning |
