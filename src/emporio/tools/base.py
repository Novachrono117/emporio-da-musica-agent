"""What every tool shares: the session context, input validation, prices and the text formats the model reads.

Schemas are written by hand and use only what Claude's strict tool use accepts: types, enum, required and
additionalProperties false (decision D-006). Ranges and rules across fields are checked by the tools, which raise
ToolError; the registry turns it into a structured error the model can read and correct.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from emporio.config import agent_now
from emporio.data.models import Product, Promotion
from emporio.data.policy import PolicyManual
from emporio.data.repository import StoreRepository
from emporio.tickets import TicketLog

CENT = Decimal("0.01")

Result = dict[str, Any]


class ToolError(Exception):
    """A request the tool cannot answer. The code and message go back to the model, never a stack trace."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ToolContext:
    """What the tools of one conversation share; the agent creates one per session."""

    store: StoreRepository
    manual: PolicyManual
    tickets: TicketLog
    now: Callable[[], datetime] = agent_now  # store time (D-005, rule 7)
    failed_order_lookups: int = 0  # session state for get_order_status (D-005, rule 11)
    seen_products: set[int] = field(default_factory=set)  # ids the catalog tools returned; quotes need one (D-008)
    last_failed_lookup: tuple[int, str] | None = None  # a repeated identical lookup is not a new attempt

    def today(self) -> date:
        return self.now().date()


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    handler: Callable[..., Result]


def validate_arguments(schema: Mapping[str, Any], arguments: object) -> dict[str, Any]:
    """Check the model's arguments against a tool schema and return them typed (numbers as Decimal).

    A null optional argument counts as absent: OpenAI-compatible models often send null for what they leave out.
    """
    if not isinstance(arguments, Mapping):
        raise ToolError("invalid_input", "arguments must be a JSON object")
    return _object(schema, arguments, "")


def _object(schema: Mapping[str, Any], value: Mapping[str, Any], path: str) -> dict[str, Any]:
    properties = schema["properties"]
    unknown = sorted(set(value) - set(properties))
    if unknown:
        raise ToolError("invalid_input", f"unexpected argument: {', '.join(_join(path, name) for name in unknown)}")
    result = {}
    for name, prop in properties.items():
        item = value.get(name)
        if item is None:
            if name in schema.get("required", ()):
                raise ToolError("invalid_input", f"missing required argument: {_join(path, name)}")
            continue
        result[name] = _value(prop, item, _join(path, name))
    return result


def _value(prop: Mapping[str, Any], value: object, path: str) -> object:
    kind = prop["type"]
    if kind == "string" and isinstance(value, str):
        value = value.strip()
        if "enum" in prop and value not in prop["enum"]:
            raise ToolError("invalid_input", f"{path} must be one of: {', '.join(prop['enum'])}")
        return value
    if kind == "integer" and _is_number(value) and value == int(value):
        return int(value)
    if kind == "number" and _is_number(value):
        return Decimal(str(value))
    if kind == "boolean" and isinstance(value, bool):
        return value
    if kind == "array" and isinstance(value, list):
        return [_value(prop["items"], item, f"{path}[{index}]") for index, item in enumerate(value)]
    if kind == "object" and isinstance(value, Mapping):
        return _object(prop, value, path)
    raise ToolError("invalid_input", f"{path} must be of type {kind}")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _join(path: str, name: str) -> str:
    return f"{path}.{name}" if path else name


def current_price(store: StoreRepository, product: Product) -> tuple[Decimal, Promotion | None]:
    """The price a customer pays today: the list price, or the active promotion's price (6.2)."""
    promotion = store.active_promotion(product.id)
    if promotion is None:
        return product.price, None
    return percent_off(product.price, promotion.discount_percent), promotion


def percent_off(amount: Decimal, percent: int | Decimal) -> Decimal:
    return (amount * (100 - Decimal(percent)) / 100).quantize(CENT, ROUND_HALF_UP)


def brl(amount: Decimal) -> str:
    """Brazilian money format: R$ 1.234,56."""
    text = f"{amount.quantize(CENT, ROUND_HALF_UP):,.2f}"
    return "R$ " + text.replace(",", "_").replace(".", ",").replace("_", ".")


def br_date(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def parse_date(text: str, name: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ToolError("invalid_input", f"{name} must be a date in the format YYYY-MM-DD") from None
