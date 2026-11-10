"""Contract tests for the models generated from the snapshot schema.

These are the first line of defence for AGENTS.md §5: if the schema moves and the
generated models do not, or the models stop speaking camelCase on the wire, this fails.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.models import MarketSnapshot

EXAMPLES = Path(__file__).resolve().parents[3] / "shared/schema/examples"


def load(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_valid_example_is_accepted() -> None:
    snapshot = MarketSnapshot.model_validate(load("snapshot.valid.json"))

    assert snapshot.schema_version == 1
    assert snapshot.sentiment.position == 53
    assert snapshot.indexes[0].symbol == "^GSPC"
    assert snapshot.sentiment.components is not None
    assert len(snapshot.sentiment.components) == 5


def test_serialisation_uses_the_contract_field_names() -> None:
    example = load("snapshot.valid.json")
    payload = json.loads(MarketSnapshot.model_validate(example).model_dump_json())

    assert set(payload) == set(example)
    assert payload["feedDelaySeconds"] == 900
    assert "feed_delay_seconds" not in payload


def test_negative_example_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MarketSnapshot.model_validate(load("snapshot.invalid.json"))


@pytest.mark.parametrize("extra_field", ["extra", "schemaVersionTypo"])
def test_unknown_wire_field_is_rejected(extra_field: str) -> None:
    example = load("snapshot.valid.json")
    example[extra_field] = 1

    with pytest.raises(ValidationError):
        MarketSnapshot.model_validate(example)


def test_implausible_values_are_rejected() -> None:
    example = load("snapshot.valid.json")
    example["indexes"][0]["price"] = 0

    with pytest.raises(ValidationError):
        MarketSnapshot.model_validate(example)
