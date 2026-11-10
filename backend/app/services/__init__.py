"""Pure-ish business logic: snapshot building, sentiment, market hours, movers filtering.

Modules here must not read the clock or the network directly; inputs are passed in so a
recorded snapshot can be replayed and asserted (AGENTS.md §8).
"""
