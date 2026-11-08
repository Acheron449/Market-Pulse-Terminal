#!/usr/bin/env python3
"""Validate the snapshot JSON Schema and its example snapshots.

Runs in CI (.github/workflows/ci.yml) and locally:

    python scripts/validate_schema.py

Checks, in order:

1. the schema parses with no duplicate keys and conforms to the draft-2020-12 metaschema;
2. every ``*.valid.json`` example is accepted;
3. every ``*.invalid.json`` example is rejected, which proves the gate still enforces
   something instead of passing an empty schema.

The ``jsonschema`` package is a development and CI dependency, never a runtime one;
the workflow installs it before calling this script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA = ROOT / "shared/schema/market-snapshot.schema.json"
DEFAULT_EXAMPLES = ROOT / "shared/schema/examples"


def load_json(path: Path) -> Any:
    """Parse JSON, rejecting duplicate keys instead of silently keeping the last one."""

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the snapshot schema against its metaschema and its examples."
    )
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--examples", type=Path, default=DEFAULT_EXAMPLES)
    args = parser.parse_args()

    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError:
        print(
            "jsonschema is required: pip install 'jsonschema>=4.18,<5'",
            file=sys.stderr,
        )
        return 2

    try:
        schema = load_json(args.schema)
    except (OSError, ValueError) as exc:
        print(f"cannot read schema: {exc}", file=sys.stderr)
        return 1

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        print(f"schema is not valid draft 2020-12: {exc.message}", file=sys.stderr)
        return 1
    print(f"ok  schema conforms to the 2020-12 metaschema: {args.schema}")

    if not args.examples.is_dir():
        print(f"examples directory not found: {args.examples}", file=sys.stderr)
        return 1

    valid_files = sorted(args.examples.glob("*.valid.json"))
    invalid_files = sorted(args.examples.glob("*.invalid.json"))
    if not valid_files:
        print(f"no *.valid.json examples in {args.examples}", file=sys.stderr)
        return 1
    if not invalid_files:
        print(f"no *.invalid.json examples in {args.examples}", file=sys.stderr)
        return 1

    validator = Draft202012Validator(schema)
    failures = 0

    for path in valid_files:
        try:
            instance = load_json(path)
        except (OSError, ValueError) as exc:
            print(f"FAIL {path.name}: {exc}")
            failures += 1
            continue
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
        if errors:
            failures += 1
            print(f"FAIL {path.name}: expected valid, found {len(errors)} error(s)")
            for error in errors[:5]:
                where = "/".join(str(part) for part in error.path) or "<root>"
                print(f"     {where}: {error.message}")
        else:
            print(f"ok  {path.name} validates")

    for path in invalid_files:
        try:
            instance = load_json(path)
        except (OSError, ValueError) as exc:
            print(f"FAIL {path.name}: unreadable negative example: {exc}")
            failures += 1
            continue
        errors = list(validator.iter_errors(instance))
        if errors:
            where = "/".join(str(part) for part in errors[0].path) or "<root>"
            print(f"ok  {path.name} rejected as intended ({len(errors)} error(s), first at {where})")
        else:
            failures += 1
            print(f"FAIL {path.name}: expected rejection but it validated; the gate is too weak")

    if failures:
        print(f"\n{failures} example(s) failed", file=sys.stderr)
        return 1

    print(
        f"\n{len(valid_files)} valid and {len(invalid_files)} invalid example(s) "
        "behaved as expected"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
