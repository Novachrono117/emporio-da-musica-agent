"""Shared fixtures: the real store data, the policy manual and a tool context at a fixed store time."""

from datetime import datetime

import pytest

from emporio.config import STORE_TZ
from emporio.data.memory import InMemoryStore
from emporio.data.policy import load_policy_manual
from emporio.llm.base import LLMResponse, ToolCall, Usage
from emporio.tickets import TicketLog
from emporio.tools.base import ToolContext

# Monday, the default "today" (D-005, rule 7), during business hours.
MONDAY_10AM = datetime(2026, 3, 23, 10, 0, tzinfo=STORE_TZ)


@pytest.fixture(scope="session")
def store():
    return InMemoryStore.from_csv()


@pytest.fixture(scope="session")
def manual():
    return load_policy_manual()


@pytest.fixture
def ctx(store, manual, tmp_path):
    return ToolContext(store, manual, TicketLog(tmp_path / "tickets.jsonl"), now=lambda: MONDAY_10AM)


class ScriptedLLM:
    """A fake LLMClient that returns prepared responses in order and records what it was sent."""

    provider = "scripted"
    model = "scripted-1"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, system, messages, tools):
        self.calls.append({"system": system, "messages": [dict(m) for m in messages], "tools": tools})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def text(answer):
    return LLMResponse(answer, (), "end", Usage(100, 10), raw={"text": answer})


def tools(*calls):
    """A response asking for tools: tools(("search_products", {"query": "x"}), ...)."""
    tool_calls = tuple(ToolCall(f"call_{i}", name, args) for i, (name, args) in enumerate(calls))
    return LLMResponse("", tool_calls, "tool_use", Usage(100, 10, cached_input_tokens=80), raw={"calls": len(calls)})
