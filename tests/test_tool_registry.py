"""Tool definitions, schema validation and dispatch (decision D-006)."""

from decimal import Decimal

import pytest

from emporio.tools.base import ToolError, brl, validate_arguments
from emporio.tools.registry import TOOLS, run_tool, tool_definitions

# Claude's strict tool use rejects these keywords; ranges are checked in code instead.
UNSUPPORTED_IN_STRICT = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength",
                         "maxLength", "minItems", "maxItems"}

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "kind": {"type": "string", "enum": ["a", "b"]},
        "count": {"type": "integer"},
        "price": {"type": "number"},
        "flag": {"type": "boolean"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["name"],
    "additionalProperties": False,
}


def _objects(schema):
    if schema.get("type") == "object":
        yield schema
        for prop in schema["properties"].values():
            yield from _objects(prop)
    elif schema.get("type") == "array":
        yield from _objects(schema["items"])


def _keywords(schema):
    if isinstance(schema, dict):
        for key, value in schema.items():
            yield key
            if key == "properties":
                for prop in value.values():
                    yield from _keywords(prop)
            elif isinstance(value, dict):
                yield from _keywords(value)


def test_definitions_are_unique_and_described():
    definitions = tool_definitions()
    assert len({d["name"] for d in definitions}) == len(definitions) == len(TOOLS)
    assert all(d["description"] and d["input_schema"]["type"] == "object" for d in definitions)


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_schemas_fit_claude_strict_mode(tool):
    for obj in _objects(tool.input_schema):
        assert obj["additionalProperties"] is False
        assert set(obj.get("required", ())) <= set(obj["properties"])
    assert all(prop.get("description") for prop in tool.input_schema["properties"].values())
    assert not UNSUPPORTED_IN_STRICT & set(_keywords(tool.input_schema))


def test_validation_types_the_arguments():
    args = validate_arguments(SCHEMA, {"name": " x ", "kind": "a", "count": 2.0, "price": 9.9, "flag": False,
                                       "items": [{"id": 3}]})
    assert args == {"name": "x", "kind": "a", "count": 2, "price": Decimal("9.9"), "flag": False, "items": [{"id": 3}]}
    assert isinstance(args["count"], int)


def test_null_optional_arguments_count_as_absent():
    assert validate_arguments(SCHEMA, {"name": "x", "count": None}) == {"name": "x"}


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({}, "missing required argument: name"),
        ({"name": "x", "extra": 1}, "unexpected argument: extra"),
        ({"name": "x", "kind": "c"}, "kind must be one of: a, b"),
        ({"name": "x", "count": 2.5}, "count must be of type integer"),
        ({"name": "x", "count": True}, "count must be of type integer"),
        ({"name": "x", "price": "10"}, "price must be of type number"),
        ({"name": "x", "price": float("nan")}, "price must be of type number"),
        ({"name": "x", "items": [{"id": 1, "qty": 2}]}, "unexpected argument: items[0].qty"),
        ({"name": "x", "items": [{}]}, "missing required argument: items[0].id"),
        ("not an object", "arguments must be a JSON object"),
    ],
)
def test_validation_errors_name_the_argument(arguments, message):
    with pytest.raises(ToolError) as error:
        validate_arguments(SCHEMA, arguments)
    assert error.value.code == "invalid_input"
    assert message in error.value.message


def test_run_tool_returns_errors_as_data(ctx):
    assert run_tool(ctx, "no_such_tool", {})["error"]["code"] == "unknown_tool"
    assert run_tool(ctx, "search_products", {"limit": "five"})["error"] == {
        "code": "invalid_input",
        "message": "limit must be of type integer",
    }
    assert run_tool(ctx, "search_products", {"limit": 50})["error"]["code"] == "invalid_input"


@pytest.mark.parametrize(
    "amount, text",
    [("0.5", "R$ 0,50"), ("599.9", "R$ 599,90"), ("1234.567", "R$ 1.234,57"), ("19567", "R$ 19.567,00"),
     ("1000000", "R$ 1.000.000,00")],
)
def test_money_is_formatted_in_brazilian_style(amount, text):
    assert brl(Decimal(amount)) == text
