"""The adapters translate the neutral history and parse real SDK response objects, without network calls (D-008).

The SDK objects are built from the shapes each API returns; with no Anthropic credit, this is the only test of the
Claude adapter (DECISIONS.md, D-008).
"""

import json

import anthropic
import httpx2
import openai
import pytest
from anthropic.types import Message as AnthropicMessage
from openai.types import CompletionUsage
from openai.types.chat import ChatCompletion

from emporio.llm import create_client
from emporio.llm.anthropic_client import AnthropicClient
from emporio.llm.base import LLMError
from emporio.llm.openai_compat_client import OpenAICompatClient
from emporio.tools.registry import tool_definitions

TOOLS = tool_definitions()


class FakeEndpoint:
    """Stands in for client.messages or client.chat.completions: records the request, returns a canned response."""

    def __init__(self, response):
        self.response = response
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeAnthropic:
    def __init__(self, response):
        self.messages = FakeEndpoint(response)


class FakeOpenAI:
    def __init__(self, response):
        self.chat = type("Chat", (), {"completions": FakeEndpoint(response)})()


CLAUDE_TOOL_TURN = AnthropicMessage.model_validate(
    {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [
            {"type": "thinking", "thinking": "", "signature": "sig-1"},
            {"type": "text", "text": "Vou conferir."},
            {"type": "tool_use", "id": "toolu_1", "name": "search_products", "input": {"query": "Takamine"}},
        ],
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 50,
            "output_tokens": 40,
            "cache_read_input_tokens": 3000,
            "cache_creation_input_tokens": 200,
        },
    }
)

GEMINI_TOOL_TURN = ChatCompletion.model_validate(
    {
        "id": "c",
        "object": "chat.completion",
        "created": 0,
        "model": "gemini-3.5-flash-lite",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_a",
                            "type": "function",
                            "function": {"name": "search_products", "arguments": '{"query": "Takamine"}'},
                            "extra_content": {"google": {"thought_signature": "ts-1"}},
                        },
                        {
                            "id": "call_b",
                            "type": "function",
                            "function": {"name": "get_store_policy", "arguments": "not json"},
                        },
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 900,
            "completion_tokens": 30,
            "total_tokens": 930,
            "prompt_tokens_details": {"cached_tokens": 512},
        },
    }
)

HISTORY = [
    {"role": "user", "content": "Quanto custa o Takamine?"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "t1", "name": "search_products", "arguments": {"query": "Takamine"}},
            {"id": "t2", "name": "get_store_policy", "arguments": {"topic": "payment"}},
        ],
        "provider": "other",
        "raw": {"from": "another provider"},
    },
    {"role": "tool", "tool_call_id": "t1", "name": "search_products", "content": '{"products": []}'},
    {"role": "tool", "tool_call_id": "t2", "name": "get_store_policy", "content": '{"topic": "payment"}'},
    {"role": "assistant", "content": "Não achei.", "provider": "other", "raw": None},
    {"role": "user", "content": "Ok"},
]


def test_claude_request_settings():
    fake = FakeAnthropic(CLAUDE_TOOL_TURN)
    AnthropicClient("claude-haiku-5-5", client=fake).complete("system text", HISTORY[:1], TOOLS)
    [request] = fake.messages.requests
    assert request["system"] == "system text"
    assert request["output_config"] == {"effort": "low"}
    assert request["cache_control"] == {"type": "ephemeral"}
    assert all(tool["strict"] is True for tool in request["tools"])
    assert not {"temperature", "top_p", "top_k"} & set(request)


def test_claude_response_is_parsed_and_kept_raw():
    client = AnthropicClient("claude-haiku-5-5", client=FakeAnthropic(CLAUDE_TOOL_TURN))
    response = client.complete("s", HISTORY[:1], TOOLS)
    assert response.text == "Vou conferir."
    [call] = response.tool_calls
    assert (call.id, call.name, call.arguments) == ("toolu_1", "search_products", {"query": "Takamine"})
    assert response.stop_reason == "tool_use"
    assert (response.usage.input_tokens, response.usage.cached_input_tokens, response.usage.cache_write_tokens) == (
        3250, 3000, 200
    )
    assert response.raw[0] == {"type": "thinking", "thinking": "", "signature": "sig-1"}


def test_claude_replays_its_own_turn_unchanged_and_groups_tool_results():
    client = AnthropicClient("claude-haiku-5-5", client=FakeAnthropic(CLAUDE_TOOL_TURN))
    own = client.complete("s", HISTORY[:1], TOOLS).as_message("anthropic")
    history = [HISTORY[0], own, {"role": "tool", "tool_call_id": "toolu_1", "name": "search_products", "content": "{}"}]
    turns = client.to_messages(history)
    assert turns[1] == {"role": "assistant", "content": own["raw"]}  # thinking block included
    assert turns[2] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "{}"}]}


def test_claude_rebuilds_turns_from_another_provider():
    turns = AnthropicClient("claude-haiku-5-5", client=FakeAnthropic(None)).to_messages(HISTORY)
    assert [t["role"] for t in turns] == ["user", "assistant", "user", "assistant", "user"]
    assert turns[1]["content"] == [
        {"type": "tool_use", "id": "t1", "name": "search_products", "input": {"query": "Takamine"}},
        {"type": "tool_use", "id": "t2", "name": "get_store_policy", "input": {"topic": "payment"}},
    ]
    assert [block["tool_use_id"] for block in turns[2]["content"]] == ["t1", "t2"]
    assert turns[3]["content"] == [{"type": "text", "text": "Não achei."}]


def test_gemini_response_keeps_thought_signatures_and_flags_bad_arguments():
    fake = FakeOpenAI(GEMINI_TOOL_TURN)
    client = OpenAICompatClient("gemini", "gemini-3.5-flash-lite", "http://unused", "k", client=fake)
    response = client.complete("system text", HISTORY[:1], TOOLS)
    assert [(c.name, c.arguments) for c in response.tool_calls] == [
        ("search_products", {"query": "Takamine"}),
        ("get_store_policy", None),
    ]
    assert response.stop_reason == "tool_use"
    assert (response.usage.input_tokens, response.usage.output_tokens, response.usage.cached_input_tokens) == (
        900, 30, 512
    )
    assert response.raw["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "ts-1"}}
    [request] = fake.chat.completions.requests
    assert request["messages"][0] == {"role": "system", "content": "system text"}
    assert "strict" not in json.dumps(request["tools"])
    assert request["tools"][0]["function"]["parameters"] == TOOLS[0]["input_schema"]


def test_gemini_thinking_counts_as_output():
    # Seen on 2026-11-01: thinking appears only in total_tokens, and Gemini bills it as output.
    thinking_turn = GEMINI_TOOL_TURN.model_copy(
        update={"usage": CompletionUsage(prompt_tokens=101, completion_tokens=29, total_tokens=1281)}
    )
    client = OpenAICompatClient("gemini", "m", "http://unused", "k", client=FakeOpenAI(thinking_turn))
    assert client.complete("s", HISTORY[:1], TOOLS).usage.output_tokens == 1180


def test_openai_compat_replays_its_own_turn_and_rebuilds_others():
    client = OpenAICompatClient("gemini", "m", "http://unused", "k", client=FakeOpenAI(GEMINI_TOOL_TURN))
    own = client.complete("s", HISTORY[:1], TOOLS).as_message("gemini")
    assert client.to_messages([own])[0] is own["raw"]
    turns = client.to_messages(HISTORY)
    assert turns[1]["tool_calls"][0] == {
        "id": "t1",
        "type": "function",
        "function": {"name": "search_products", "arguments": '{"query": "Takamine"}'},
    }
    assert turns[2] == {"role": "tool", "tool_call_id": "t1", "content": '{"products": []}'}
    assert turns[4] == {"role": "assistant", "content": "Não achei."}


def test_sdk_errors_become_llm_errors():
    request = httpx2.Request("POST", "http://test")
    gemini_error = openai.APIStatusError(
        "quota exceeded", response=httpx2.Response(429, request=request), body=None
    )
    client = OpenAICompatClient("gemini", "m", "http://unused", "k", client=FakeOpenAI(gemini_error))
    with pytest.raises(LLMError, match=r"gemini .*HTTP 429"):
        client.complete("s", HISTORY[:1], TOOLS)
    claude_error = anthropic.APIConnectionError(request=request)
    with pytest.raises(LLMError, match="anthropic APIConnectionError"):
        AnthropicClient("m", client=FakeAnthropic(claude_error)).complete("s", HISTORY[:1], TOOLS)


def test_missing_keys_are_reported_by_name(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY is not set"):
        create_client("anthropic")
    with pytest.raises(LLMError, match="GEMINI_API_KEY is not set"):
        create_client("gemini")
    assert create_client("ollama").model == "qwen3.5:4b"
    with pytest.raises(LLMError, match="unknown provider 'openai'"):
        create_client("openai")
