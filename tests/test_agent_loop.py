"""The tool-calling loop with a scripted LLM (PLAN, section 8; decision D-008)."""

import json

import pytest
from conftest import MONDAY_10AM, ScriptedLLM, text, tools

from emporio.agent.loop import FALLBACK_ANSWER, MAX_TOOL_ROUNDS, Agent
from emporio.agent.memory import new_session
from emporio.agent.usage import UsageLog
from emporio.llm.base import LLMError, LLMResponse, ToolCall
from emporio.tools.base import ToolContext


@pytest.fixture
def session():
    return new_session("scripted", "scripted-1", MONDAY_10AM)


def _agent(llm, ctx, session, tmp_path=None, **kwargs):
    usage = UsageLog(tmp_path / "usage.jsonl") if tmp_path else None
    return Agent(llm, ctx, session, usage, **kwargs)


def _results(messages):
    return [json.loads(m["content"]) for m in messages if m["role"] == "tool"]


def test_tool_round_trip(ctx, session):
    llm = ScriptedLLM(tools(("search_products", {"query": "Takamine GD20"})), text("Custa R$ 2.199,00."))
    assert _agent(llm, ctx, session).reply("Quanto custa o Takamine GD20?") == "Custa R$ 2.199,00."
    roles = [m["role"] for m in session.messages]
    assert roles == ["user", "assistant", "tool", "assistant"]
    assert session.messages[1]["tool_calls"] == [
        {"id": "call_0", "name": "search_products", "arguments": {"query": "Takamine GD20"}}
    ]
    assert session.messages[1]["provider"] == "scripted" and session.messages[1]["raw"] == {"calls": 1}
    [result] = _results(session.messages)
    assert result["products"][0]["price"] == "R$ 2.199,00"
    # The second call sees the tool result, the system prompt carries the store date and every tool is offered.
    assert llm.calls[1]["messages"][-1]["role"] == "tool"
    assert "segunda-feira, 23/03/2026" in llm.calls[1]["system"]
    assert len(llm.calls[1]["tools"]) == 8


def test_several_tool_calls_in_one_response_all_get_results(ctx, session):
    llm = ScriptedLLM(
        tools(("search_products", {"query": "Takamine GD20"}), ("get_store_policy", {"topic": "hours"})),
        text("Pronto."),
    )
    _agent(llm, ctx, session).reply("oi")
    assert [m.get("tool_call_id") for m in session.messages if m["role"] == "tool"] == ["call_0", "call_1"]


def test_tool_errors_go_back_to_the_model(ctx, session):
    quote = {"items": [{"product_id": 95, "quantity": 1}], "method": "pix"}
    llm = ScriptedLLM(tools(("quote_payment", quote)), text("ok"))
    _agent(llm, ctx, session).reply("Quanto fica no Pix?")
    [result] = _results(session.messages)
    assert result["error"]["code"] == "unknown_product_id"  # never looked up in this session


def test_arguments_that_are_not_an_object_become_an_error_result(ctx, session):
    bad = LLMResponse("", (ToolCall("c1", "search_products", None),), "tool_use")
    _agent(ScriptedLLM(bad, text("ok")), ctx, session).reply("oi")
    [result] = _results(session.messages)
    assert result == {"error": {"code": "invalid_input", "message": "arguments must be a JSON object"}}


def test_a_crashing_tool_does_not_end_the_conversation(ctx, session, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr("emporio.agent.loop.run_tool", boom)
    _agent(ScriptedLLM(tools(("search_products", {})), text("Desculpe.")), ctx, session).reply("oi")
    assert _results(session.messages)[0]["error"]["code"] == "internal_error"


def test_a_seventh_tool_round_is_dropped_for_the_fixed_answer(ctx, session):
    rounds = [tools(("get_store_policy", {"topic": "hours"})) for _ in range(MAX_TOOL_ROUNDS + 1)]
    llm = ScriptedLLM(*rounds)
    assert _agent(llm, ctx, session).reply("oi") == FALLBACK_ANSWER
    assert len(llm.calls) == MAX_TOOL_ROUNDS + 1
    # Six rounds ran; the seventh request left no tool call without a result.
    calls = [c["id"] for m in session.messages if m["role"] == "assistant" for c in m.get("tool_calls", [])]
    results = [m["tool_call_id"] for m in session.messages if m["role"] == "tool"]
    assert len(results) == MAX_TOOL_ROUNDS and len(calls) == len(results)
    assert session.messages[-1] == {
        "role": "assistant",
        "content": FALLBACK_ANSWER,
        "provider": "scripted",
        "raw": None,
    }
    assert "(67) 3321-4500" in FALLBACK_ANSWER


@pytest.mark.parametrize("response", [LLMResponse("", (), "refusal"), LLMResponse("   ", (), "end")])
def test_refusals_and_empty_answers_get_the_fixed_answer(ctx, session, response):
    assert _agent(ScriptedLLM(response), ctx, session).reply("oi") == FALLBACK_ANSWER


def test_provider_failure_leaves_the_history_as_it_was(ctx, session):
    llm = ScriptedLLM(text("Olá!"), tools(("search_products", {"query": "violão"})), LLMError("503"))
    agent = _agent(llm, ctx, session)
    agent.reply("oi")
    before = list(session.messages)
    with pytest.raises(LLMError):
        agent.reply("tem violão?")
    assert session.messages == before


def test_tool_state_lives_in_the_session(ctx, session, store, manual):
    llm = ScriptedLLM(
        tools(("get_order_status", {"order_id": 8, "phone_last4": "0000"}), ("search_products", {"query": "GD20"})),
        text("ok"),
    )
    _agent(llm, ctx, session).reply("meu pedido")
    assert (session.failed_order_lookups, session.seen_products) == (1, [95])
    # A resumed session brings its state into a fresh tool context.
    fresh = ToolContext(store, manual, ctx.tickets, now=ctx.now)
    _agent(ScriptedLLM(), fresh, session)
    assert (fresh.failed_order_lookups, fresh.seen_products) == (1, {95})


def test_usage_is_logged_without_conversation_text(ctx, session, tmp_path):
    llm = ScriptedLLM(tools(("search_products", {"query": "Takamine GD20"})), text("Custa R$ 2.199,00."))
    _agent(llm, ctx, session, tmp_path).reply("Quanto custa o Takamine GD20?")
    lines = (tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    first, second = map(json.loads, lines)
    assert first["tools"] == ["search_products"] and second["tools"] == []
    assert (first["input_tokens"], first["cached_input_tokens"], first["session_id"]) == (100, 80, session.id)
    assert "Takamine" not in "".join(lines)


def test_on_tool_sees_every_call(ctx, session):
    seen = []
    llm = ScriptedLLM(tools(("get_store_policy", {"topic": "hours"})), text("ok"))
    _agent(llm, ctx, session, on_tool=lambda call, result: seen.append((call.name, result["topic"]))).reply("oi")
    assert seen == [("get_store_policy", "hours")]
