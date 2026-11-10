#!/usr/bin/env python3
"""Generate the backend Pydantic models and frontend TypeScript types from the schema.

Usage:
    ./scripts/gen_types.sh            # rewrite both generated files
    ./scripts/gen_types.sh --check    # exit 1 when either file is stale (runs in CI)

The schema is the single source of truth (AGENTS.md §5). This generator understands
exactly the JSON Schema subset the contract uses and refuses to run on anything else,
so a schema change can never silently produce wrong or half-generated types.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "shared/schema/market-snapshot.schema.json"
PYTHON_PATH = ROOT / "backend/app/models/market_snapshot.py"
TYPESCRIPT_PATH = ROOT / "frontend/src/types/market-snapshot.ts"

ROOT_CLASS = "MarketSnapshot"
LINE_WIDTH = 88

# Names other modules import, so they must not be derived mechanically.
ENUM_ALIASES: dict[tuple[str, str], str] = {
    ("sentiment", "verdict"): "Verdict",
    ("sentiment", "marketStatus"): "MarketStatus",
    ("component", "name"): "ComponentName",
}

# Map properties become reusable dictionary types.
MAP_ALIASES: dict[str, str] = {"sources": "SourceMap", "status": "SectionStatusMap"}

# `Error` shadows the builtin, `Symbol` collides with the TypeScript global, and
# `Index` reads badly as a model name.
RENAMES: dict[str, str] = {
    "error": "SnapshotError",
    "symbol": "TickerSymbol",
    "index": "IndexCard",
}

SUPPORTED_KEYWORDS = {
    "$schema",
    "$id",
    "$defs",
    "$ref",
    "title",
    "description",
    "type",
    "const",
    "enum",
    "default",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minProperties",
    "allOf",
    "if",
    "then",
    "else",
    "examples",
    "deprecated",
}


class GenError(RuntimeError):
    """The schema uses something this generator cannot express."""


def type_name(defname: str) -> str:
    """Public type name for a schema definition key."""
    if defname in RENAMES:
        return RENAMES[defname]
    return defname[:1].upper() + defname[1:]


def py_field_name(prop: str) -> str:
    """camelCase contract name to snake_case Python attribute."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", prop).lower()


def py_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    if isinstance(value, str):
        return json.dumps(value)
    return repr(value)


def pattern_constant(hint: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", hint).upper() + "_PATTERN"


def check_keywords(node: Any, where: str) -> None:
    """Fail on any keyword this generator does not model, instead of ignoring it."""
    if not isinstance(node, dict):
        return
    unknown = set(node) - SUPPORTED_KEYWORDS
    if unknown:
        raise GenError(
            f"{where}: unsupported keyword(s) {sorted(unknown)}; extend the generator first"
        )
    for name, sub in node.get("properties", {}).items():
        check_keywords(sub, f"{where}.properties.{name}")
    if isinstance(node.get("items"), dict):
        check_keywords(node["items"], f"{where}.items")
    if isinstance(node.get("additionalProperties"), dict):
        check_keywords(node["additionalProperties"], f"{where}.additionalProperties")
    for key in ("allOf", "anyOf", "oneOf"):
        for index, sub in enumerate(node.get(key, [])):
            check_keywords(sub, f"{where}.{key}[{index}]")
    for key in ("if", "then", "else"):
        if isinstance(node.get(key), dict):
            check_keywords(node[key], f"{where}.{key}")
    for name, sub in node.get("$defs", {}).items():
        check_keywords(sub, f"{where}.$defs.{name}")


def collect_patterns(schema: dict[str, Any]) -> dict[str, str]:
    """Pattern string to the constant name both generated files expose."""
    patterns: dict[str, str] = {}

    def record(node: Any, hint: str) -> None:
        if not isinstance(node, dict):
            return
        if "pattern" in node:
            patterns.setdefault(node["pattern"], pattern_constant(hint))
        for name, sub in node.get("properties", {}).items():
            record(sub, name)
        if isinstance(node.get("items"), dict):
            record(node["items"], hint)
        if isinstance(node.get("additionalProperties"), dict):
            record(node["additionalProperties"], hint)

    for defname, node in schema["$defs"].items():
        record(node, type_name(defname))
    for prop, node in schema["properties"].items():
        record(node, prop)
    return patterns


def collect_definitions(
    schema: dict[str, Any],
) -> tuple[
    dict[str, list[Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[tuple[str, str], str],
]:
    """Split the definitions into enums, scalars, objects and inline enums."""
    enums: dict[str, list[Any]] = {}
    scalars: dict[str, dict[str, Any]] = {}
    objects: dict[str, dict[str, Any]] = {}
    inline_enums: dict[tuple[str, str], str] = {}

    for defname, node in schema["$defs"].items():
        if "enum" in node:
            enums[type_name(defname)] = list(node["enum"])
        elif "properties" in node:
            objects[type_name(defname)] = node
        elif node.get("type") in {"string", "number", "integer", "boolean"}:
            scalars[type_name(defname)] = node
        else:
            raise GenError(f"$defs/{defname}: unsupported definition")

    for defname, node in schema["$defs"].items():
        for prop, sub in node.get("properties", {}).items():
            if "enum" not in sub:
                continue
            alias = ENUM_ALIASES.get((defname, prop))
            if alias is None:
                alias = type_name(defname) + prop[:1].upper() + prop[1:]
            inline_enums[(type_name(defname), prop)] = alias
            enums[alias] = list(sub["enum"])

    return enums, scalars, objects, inline_enums


def py_constraints(node: dict[str, Any], patterns: dict[str, str]) -> list[str]:
    """Field keyword arguments for the inline constraints on a schema node."""
    args: list[str] = []
    if "pattern" in node:
        args.append(f"pattern={patterns[node['pattern']]}")
    for key, keyword in (("minLength", "min_length"), ("maxLength", "max_length")):
        if key in node:
            args.append(f"{keyword}={node[key]}")
    for key, keyword in (("minItems", "min_length"), ("maxItems", "max_length")):
        if key in node:
            args.append(f"{keyword}={node[key]}")
    if "minimum" in node:
        args.append(f"ge={node['minimum']}")
    if "maximum" in node:
        args.append(f"le={node['maximum']}")
    if "exclusiveMinimum" in node:
        args.append(f"gt={node['exclusiveMinimum']}")
    if "exclusiveMaximum" in node:
        args.append(f"lt={node['exclusiveMaximum']}")
    return args


def py_annotation(
    node: dict[str, Any],
    owner: str,
    prop: str,
    inline_enums: dict[tuple[str, str], str],
) -> str:
    if prop in MAP_ALIASES and (
        "properties" in node or isinstance(node.get("additionalProperties"), dict)
    ):
        return MAP_ALIASES[prop]
    reference = node.get("$ref")
    if isinstance(reference, str):
        if not reference.startswith("#/$defs/"):
            raise GenError(f"only local #/$defs refs are supported, got {reference!r}")
        return type_name(reference.rsplit("/", 1)[-1])
    if "enum" in node:
        alias = inline_enums.get((owner, prop))
        if alias is None:
            raise GenError(f"{owner}.{prop}: enum without a registered alias")
        return alias
    if "const" in node:
        return f"Literal[{py_literal(node['const'])}]"
    kind = node.get("type")
    if kind == "string":
        return "str"
    if kind == "number":
        return "float"
    if kind == "integer":
        return "int"
    if kind == "boolean":
        return "bool"
    if kind == "array":
        items = node.get("items")
        if not isinstance(items, dict):
            raise GenError(f"{owner}.{prop}: array without an item schema")
        return f"list[{py_annotation(items, owner, prop, inline_enums)}]"
    raise GenError(f"{owner}.{prop}: cannot express {sorted(node)} in Python")


def py_class(
    name: str,
    obj: dict[str, Any],
    owner: str,
    inline_enums: dict[tuple[str, str], str],
    patterns: dict[str, str],
) -> list[str]:
    required = set(obj.get("required", []))
    lines = [f"class {name}(_SnapshotModel):"]
    description = obj.get("description")
    if description:
        lines.append(f'    """{description}"""')
        lines.append("")

    for prop, node in obj["properties"].items():
        attribute = py_field_name(prop)
        annotation = py_annotation(node, owner, prop, inline_enums)
        is_required = prop in required
        if not is_required and "default" not in node:
            annotation = f"{annotation} | None"

        args: list[str] = []
        if not is_required:
            args.append(f"default={py_literal(node.get('default'))}")
        if attribute != prop:
            args.append(f'alias="{prop}"')
        args.extend(py_constraints(node, patterns))
        if node.get("description"):
            args.append(f"description={json.dumps(node['description'], ensure_ascii=False)}")

        if args:
            lines.append(f"    {attribute}: {annotation} = Field(")
            lines.extend(f"        {arg}," for arg in args)
            lines.append("    )")
        else:
            lines.append(f"    {attribute}: {annotation}")

    if "allOf" in obj:
        lines.append("")
        lines.append("    # Schema-only rule (allOf/if/then): not expressible as a type,")
        lines.append("    # enforced by the snapshot builder and the contract tests.")
    return lines


def object_order(objects: dict[str, dict[str, Any]]) -> list[str]:
    """Dependency order, so every referenced model exists before it is used."""
    order: list[str] = []
    done: set[str] = set()
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in done:
            return
        if name in visiting:
            raise GenError(f"cyclic $ref involving {name}")
        visiting.add(name)
        for node in objects[name].get("properties", {}).values():
            for candidate in (node, node.get("items")):
                if isinstance(candidate, dict) and isinstance(candidate.get("$ref"), str):
                    dependency = type_name(candidate["$ref"].rsplit("/", 1)[-1])
                    if dependency in objects:
                        visit(dependency)
        visiting.discard(name)
        done.add(name)
        order.append(name)

    for name in objects:
        visit(name)
    return order


def emit_python(
    schema: dict[str, Any],
    enums: dict[str, list[Any]],
    scalars: dict[str, dict[str, Any]],
    objects: dict[str, dict[str, Any]],
    inline_enums: dict[tuple[str, str], str],
    patterns: dict[str, str],
) -> str:
    blocks: list[str] = []

    header = [
        '"""Pydantic models for the market snapshot contract.',
        "",
        "Generated by ``scripts/gen_types.py`` from ``shared/schema/market-snapshot.schema.json``.",
        "Do not edit: change the schema, then run ``./scripts/gen_types.sh`` (AGENTS.md §5).",
        "",
        "Wire names stay camelCase in JSON: models accept either name on input",
        "(``populate_by_name``) and always serialise with the schema's names",
        "(``serialize_by_alias``, pydantic 2.11+), so ``model_dump_json()`` is",
        "schema-shaped without callers passing ``by_alias=True``.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Annotated, Any, Literal, TypeAlias",
        "",
        "from pydantic import AfterValidator, BaseModel, ConfigDict, Field",
    ]
    blocks.append("\n".join(header))

    if patterns:
        blocks.append(
            "\n".join(
                f'{constant} = r"{pattern}"' for pattern, constant in patterns.items()
            )
        )

    if enums:
        blocks.append(
            "\n".join(
                f"{name}: TypeAlias = Literal[{', '.join(json.dumps(v) for v in values)}]"
                for name, values in enums.items()
            )
        )

    scalar_lines: list[str] = []
    for name, node in scalars.items():
        args = py_constraints(node, patterns)
        base = py_annotation(node, "", name, inline_enums)
        if not args:
            scalar_lines.append(f"{name}: TypeAlias = {base}")
            continue
        one_line = f"{name}: TypeAlias = Annotated[{base}, Field({', '.join(args)})]"
        if len(one_line) <= LINE_WIDTH:
            scalar_lines.append(one_line)
        else:
            scalar_lines.extend(
                [
                    f"{name}: TypeAlias = Annotated[",
                    f"    {base},",
                    f"    Field({', '.join(args)}),",
                    "]",
                ]
            )
    if scalar_lines:
        blocks.append("\n".join(scalar_lines))

    blocks.append(
        "\n".join(
            [
                "def _require_one_entry(value: dict[str, Any]) -> dict[str, Any]:",
                '    """Reject an empty mapping, which the schema forbids (minProperties: 1)."""',
                "    if not value:",
                '        raise ValueError("must contain at least one entry")',
                "    return value",
                "",
                "SourceMap: TypeAlias = Annotated[",
                "    dict[str, Annotated[str, Field(min_length=1)]],",
                "    AfterValidator(_require_one_entry),",
                "]",
                "",
                "SectionStatusMap: TypeAlias = Annotated[",
                "    dict[str, SectionStatus],",
                "    AfterValidator(_require_one_entry),",
                "]",
            ]
        )
    )

    blocks.append(
        "\n".join(
            [
                "class _SnapshotModel(BaseModel):",
                '    """Strict shared config: the JSON contract has no unknown fields."""',
                "",
                "    model_config = ConfigDict(",
                '        extra="forbid",',
                "        allow_inf_nan=False,",
                "        populate_by_name=True,",
                "        serialize_by_alias=True,",
                "    )",
            ]
        )
    )

    for name in object_order(objects):
        blocks.append("\n".join(py_class(name, objects[name], name, inline_enums, patterns)))

    root_obj = {
        "properties": schema["properties"],
        "required": schema["required"],
        "description": f"{schema['title']} (SRS §6).",
    }
    blocks.append("\n".join(py_class(ROOT_CLASS, root_obj, "", inline_enums, patterns)))

    return "\n\n\n".join(blocks).rstrip() + "\n"


def ts_annotation(
    node: dict[str, Any],
    owner: str,
    prop: str,
    inline_enums: dict[tuple[str, str], str],
) -> str:
    if prop in MAP_ALIASES and (
        "properties" in node or isinstance(node.get("additionalProperties"), dict)
    ):
        return MAP_ALIASES[prop]
    reference = node.get("$ref")
    if isinstance(reference, str):
        if not reference.startswith("#/$defs/"):
            raise GenError(f"only local #/$defs refs are supported, got {reference!r}")
        return type_name(reference.rsplit("/", 1)[-1])
    if "enum" in node:
        alias = inline_enums.get((owner, prop))
        if alias is None:
            raise GenError(f"{owner}.{prop}: enum without a registered alias")
        return alias
    if "const" in node:
        return json.dumps(node["const"])
    kind = node.get("type")
    if kind == "string":
        return "string"
    if kind in {"number", "integer"}:
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "array":
        items = node.get("items")
        if not isinstance(items, dict):
            raise GenError(f"{owner}.{prop}: array without an item schema")
        return f"Array<{ts_annotation(items, owner, prop, inline_enums)}>"
    raise GenError(f"{owner}.{prop}: cannot express {sorted(node)} in TypeScript")


def ts_interface(
    name: str,
    obj: dict[str, Any],
    owner: str,
    inline_enums: dict[tuple[str, str], str],
) -> list[str]:
    required = set(obj.get("required", []))
    lines: list[str] = []
    if obj.get("description"):
        lines.append(f"/** {obj['description']} */")
    lines.append(f"export interface {name} {{")
    for prop, node in obj["properties"].items():
        if node.get("description"):
            lines.append(f"  /** {node['description']} */")
        optional = "" if prop in required else "?"
        lines.append(
            f"  {prop}{optional}: {ts_annotation(node, owner, prop, inline_enums)};"
        )
    lines.append("}")
    return lines


def emit_typescript(
    schema: dict[str, Any],
    enums: dict[str, list[Any]],
    scalars: dict[str, dict[str, Any]],
    objects: dict[str, dict[str, Any]],
    inline_enums: dict[tuple[str, str], str],
) -> str:
    blocks: list[str] = [
        "\n".join(
            [
                "/**",
                " * Generated from shared/schema/market-snapshot.schema.json by scripts/gen_types.py.",
                " * Do not edit: change the schema, then run ./scripts/gen_types.sh (AGENTS.md §5).",
                " * Wire names are camelCase, matching the JSON contract exactly.",
                " */",
            ]
        )
    ]

    if enums:
        blocks.append(
            "\n".join(
                f"export type {name} = {' | '.join(json.dumps(v) for v in values)};"
                for name, values in enums.items()
            )
        )

    scalar_lines: list[str] = []
    for name, node in scalars.items():
        if node.get("description"):
            scalar_lines.append(f"/** {node['description']} */")
        scalar_lines.append(f"export type {name} = {ts_annotation(node, '', name, inline_enums)};")
        scalar_lines.append("")
    if scalar_lines:
        blocks.append("\n".join(scalar_lines).rstrip())

    map_lines: list[str] = []
    for prop, node in schema["properties"].items():
        alias = MAP_ALIASES.get(prop)
        if alias is None:
            continue
        if node.get("description"):
            map_lines.append(f"/** {node['description']} */")
        element = ts_annotation(node.get("additionalProperties", {}), "", prop, inline_enums)
        map_lines.append(f"export type {alias} = Record<string, {element}>;")
        map_lines.append("")
    if map_lines:
        blocks.append("\n".join(map_lines).rstrip())

    for name, obj in objects.items():
        blocks.append("\n".join(ts_interface(name, obj, name, inline_enums)))

    root_obj = {
        "properties": schema["properties"],
        "required": schema["required"],
        "description": f"{schema['title']} (SRS §6).",
    }
    blocks.append("\n".join(ts_interface(ROOT_CLASS, root_obj, "", inline_enums)))

    return "\n\n".join(blocks).rstrip() + "\n"


def build() -> tuple[str, str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    check_keywords(schema, "$")
    patterns = collect_patterns(schema)
    enums, scalars, objects, inline_enums = collect_definitions(schema)
    return (
        emit_python(schema, enums, scalars, objects, inline_enums, patterns),
        emit_typescript(schema, enums, scalars, objects, inline_enums),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate backend models and frontend types from the snapshot schema."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when a generated file is stale instead of rewriting it",
    )
    args = parser.parse_args()

    try:
        python_source, typescript_source = build()
    except (GenError, OSError) as exc:
        print(f"gen_types: {exc}", file=sys.stderr)
        return 1

    outputs = [(PYTHON_PATH, python_source), (TYPESCRIPT_PATH, typescript_source)]

    if args.check:
        stale = [
            path
            for path, source in outputs
            if not path.exists() or path.read_text(encoding="utf-8") != source
        ]
        for path in stale:
            print(f"stale: {path.relative_to(ROOT)}")
        if stale:
            print("run ./scripts/gen_types.sh and commit the result", file=sys.stderr)
            return 1
        print("generated types are up to date")
        return 0

    for path, source in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
