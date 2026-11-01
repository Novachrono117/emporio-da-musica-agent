"""Gemini and Ollama through the openai SDK and their OpenAI-compatible endpoints (decision D-008).

Tools go without `strict`: OpenAI's strict mode requires every property to be required, and the tools have optional
ones; the tool validator checks the arguments instead. The assistant turn is kept as `message.model_dump()`, which
holds Gemini's thought signatures, and replayed as it came.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import openai

from emporio.llm.base import LLMError, LLMResponse, Message, ToolCall, Usage, replayable

TIMEOUT_S = 120  # a local model's first call loads it into memory (49 s seen on the desktop)
STOP_REASONS = {"stop": "end", "tool_calls": "tool_use", "length": "max_tokens", "content_filter": "refusal"}


class OpenAICompatClient:
    def __init__(self, provider: str, model: str, base_url: str, api_key: str, client: Any = None) -> None:
        self.provider = provider
        self.model = model
        self._client = client or openai.OpenAI(base_url=base_url, api_key=api_key, timeout=TIMEOUT_S)

    def complete(self, system: str, messages: Sequence[Message], tools: Sequence[Mapping[str, Any]]) -> LLMResponse:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, *self.to_messages(messages)],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool["description"],
                            "parameters": tool["input_schema"],
                        },
                    }
                    for tool in tools
                ],
                tool_choice="auto",
            )
        except openai.APIError as error:
            raise LLMError(_describe(self.provider, error)) from error

        choice = response.choices[0]
        message = choice.message
        calls = tuple(
            ToolCall(call.id, call.function.name, _arguments(call.function.arguments))
            for call in message.tool_calls or []
        )
        usage = response.usage
        cached = 0
        if usage and usage.prompt_tokens_details and usage.prompt_tokens_details.cached_tokens:
            cached = usage.prompt_tokens_details.cached_tokens
        return LLMResponse(
            text=message.content or "",
            tool_calls=calls,
            stop_reason=STOP_REASONS.get(choice.finish_reason or "", choice.finish_reason or ""),
            usage=Usage(usage.prompt_tokens, _output_tokens(usage), cached) if usage else Usage(),
            # Without an id on every call, a replay could not match the tool results: rebuild instead.
            raw=message.model_dump(exclude_none=True) if all(call.id for call in calls) else None,
        )

    def to_messages(self, history: Sequence[Message]) -> list[dict[str, Any]]:
        turns: list[dict[str, Any]] = []
        for message in history:
            if message["role"] == "user":
                turns.append({"role": "user", "content": message["content"]})
            elif message["role"] == "tool":
                turns.append({"role": "tool", "tool_call_id": message["tool_call_id"], "content": message["content"]})
            elif replayable(message, self.provider):
                turns.append(message["raw"])
            else:
                turn: dict[str, Any] = {"role": "assistant", "content": message["content"] or None}
                if message.get("tool_calls"):
                    turn["tool_calls"] = [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["arguments"] or {}, ensure_ascii=False),
                            },
                        }
                        for call in message["tool_calls"]
                    ]
                turns.append(turn)
        return turns


def _arguments(text: str | None) -> dict[str, Any] | None:
    try:
        value = json.loads(text or "{}")
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _output_tokens(usage: Any) -> int:
    # Gemini leaves thinking out of completion_tokens and counts it only in total_tokens (checked on 2026-11-01); it
    # is billed as output. Ollama's total is prompt plus completion, so this is completion_tokens there.
    return max(usage.completion_tokens, (usage.total_tokens or 0) - usage.prompt_tokens)


def _describe(provider: str, error: openai.APIError) -> str:
    status = getattr(error, "status_code", None)
    return f"{provider} {type(error).__name__}" + (f" (HTTP {status})" if status else "") + f": {error.message}"[:300]
