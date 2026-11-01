"""Amount check (decision D-009): an answer may cite only amounts in reais that a tool returned or the customer wrote.

Amounts are compared by value, so "R$ 1.000", "R$1000" and "R$ 1.000,00" are the same, and so is the English
"R$ 1234.56" that a small model may write for "R$ 1.234,56". Amounts written without "R$" in an answer are not
checked (known limitation); in a customer message any number counts, since customers write "até 1000".
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from emporio.llm.base import Message

_IN_REAIS = re.compile(r"R\$\s*(\d(?:[\d.,]*\d)?)")
_NUMBER = re.compile(r"\d(?:[\d.,]*\d)?")
_THOUSANDS = re.compile(r"\d{1,3}(?:\.\d{3})+")


def unsupported_amounts(answer: str, history: Iterable[Message]) -> list[str]:
    """The amounts in reais cited in `answer` that no tool result or customer message of `history` contains."""
    allowed: set[Decimal] = set()
    for message in history:
        if message["role"] == "tool":
            allowed |= {value for _, value in _amounts(_IN_REAIS, message["content"])}
        elif message["role"] == "user":
            allowed |= {value for _, value in _amounts(_NUMBER, message["content"])}
    return [f"R$ {text}" for text, value in _amounts(_IN_REAIS, answer) if value not in allowed]


def _amounts(pattern: re.Pattern[str], text: str) -> list[tuple[str, Decimal]]:
    found = []
    for match in pattern.finditer(text):
        raw = match.group(1) if pattern.groups else match.group(0)
        value = _value(raw)
        if value is not None:
            found.append((raw, value))
    return found


def _value(raw: str) -> Decimal | None:
    if "," in raw and "." in raw:
        # Whichever separator comes last is the decimal one: 1.234,56 (Brazilian) or 1,234.56 (English).
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")  # 599,90
    elif _THOUSANDS.fullmatch(raw):
        raw = raw.replace(".", "")  # 2.199 or 1.000
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None
