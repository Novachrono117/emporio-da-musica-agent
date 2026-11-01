"""Claude through the official anthropic SDK (decision D-008).

Settings read in the current docs on 2026-11-01: Claude Haiku 5.5 thinks adaptively by default; effort "low" suits a
chat route; every tool is strict; top-level cache_control caches the growing conversation. No temperature, top_p or
top_k: the API rejects them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import anthropic

from emporio.llm.base import LLMError, LLMResponse, Message, ToolCall, Usage, replayable

MAX_TOKENS = 4096  # thinking counts against it; answers are a few hundred tokens
TIMEOUT_S = 120
STOP_REASONS = {"end_turn": "end", "tool_use": "tool_use", "max_tokens": "max_tokens", "refusal": "refusal"}


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, model: str, client: Any = None) -> None:
        self.model = model
        self._client = client or anthropic.Anthropic(timeout=TIMEOUT_S)  # reads ANTHROPIC_API_KEY

    def complete(self, system: str, messages: Sequence[Message], tools: Sequence[Mapping[str, Any]]) -> LLMResponse:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=self.to_messages(messages),
                tools=[{**tool, "strict": True} for tool in tools],
                output_config={"effort": "low"},
                cache_control={"type": "ephemeral"},
            )
        except anthropic.APIError as error:
            raise LLMError(_describe(error)) from error

        usage = response.usage
        cache_read = usage.cache_read_input_tokens or 0
        cache_write = usage.cache_creation_input_tokens or 0
        return LLMResponse(
            text="".join(block.text for block in response.content if block.type == "text"),
            tool_calls=tuple(
                ToolCall(block.id, block.name, block.input if isinstance(block.input, dict) else None)
                for block in response.content
                if block.type == "tool_use"
            ),
            stop_reason=STOP_REASONS.get(response.stop_reason or "", response.stop_reason or ""),
            usage=Usage(usage.input_tokens + cache_read + cache_write, usage.output_tokens, cache_read, cache_write),
            raw=[block.model_dump(mode="json", exclude_none=True) for block in response.content],
        )

    def to_messages(self, history: Sequence[Message]) -> list[dict[str, Any]]:
        """Neutral history to Messages API turns; consecutive tool results share one user turn."""
        turns: list[dict[str, Any]] = []
        for message in history:
            if message["role"] == "user":
                turns.append({"role": "user", "content": message["content"]})
            elif message["role"] == "assistant":
                turns.append({"role": "assistant", "content": self._assistant_content(message)})
            else:
                block = {"type": "tool_result", "tool_use_id": message["tool_call_id"], "content": message["content"]}
                if turns and turns[-1]["role"] == "user" and isinstance(turns[-1]["content"], list):
                    turns[-1]["content"].append(block)
                else:
                    turns.append({"role": "user", "content": [block]})
        return turns

    def _assistant_content(self, message: Message) -> list[dict[str, Any]]:
        if replayable(message, self.provider):
            return message["raw"]  # unchanged, thinking blocks included
        content = [{"type": "text", "text": message["content"]}] if message["content"] else []
        for call in message.get("tool_calls", []):
            arguments = call["arguments"] or {}
            content.append({"type": "tool_use", "id": call["id"], "name": call["name"], "input": arguments})
        return content


def _describe(error: anthropic.APIError) -> str:
    status = getattr(error, "status_code", None)
    return f"anthropic {type(error).__name__}" + (f" (HTTP {status})" if status else "") + f": {error.message}"[:300]
