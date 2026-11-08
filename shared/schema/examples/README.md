# Snapshot examples

Two fixtures, both checked by `scripts/validate_schema.py` (and by the `schema` job in
`.github/workflows/ci.yml`):

- **`snapshot.valid.json`** — a complete, realistic `schemaVersion: 1` snapshot: five
  indices, all five mood components, mover rows with day ranges, a non-zero feed delay
  and one recorded error. It must validate.
- **`snapshot.invalid.json`** — the pre-`docs/sentiment.md` component name
  `vix_percentile` instead of `volatility`. It must be rejected.

The negative example is not decoration: without it, a schema that lost its `enum`, its
`required` list or its `$ref`s would still pass the gate. Keep both files in step with
the schema — change the schema first, then these examples (`AGENTS.md` §5).
