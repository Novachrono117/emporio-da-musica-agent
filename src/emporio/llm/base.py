"""The interface between the agent and any LLM provider (decision D-008).

The conversation history is a list of plain dicts, saved as JSON with the session:

    {"role": "user", "content": "customer text"}
    {"role": "assistant", "content": "text", "tool_calls": [{"id": ..., "name": ..., "arguments": {...}}],
     "provider": "gemini", "raw": <the provider's own form of this turn>}
    {"role": "tool", "tool_call_id": ..., "name": ..., "content": "<tool result as JSON>"}

An adapter replays `raw` unchanged when the message came from its own provider (Claude needs its thinking blocks back,
Gemini its thought signatures) and rebuilds the turn from the neutral fields otherwise.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

Message = dict[str, Any]


class LLMError(Exception):
    """The provider did not answer: network, quota, authentication or server error."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] | None  # None when the model sent arguments that are not a JSON object


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0  # every prompt token, cached ones included
    output_tokens: int = 0  # thinking included
    cached_input_tokens: int = 0  # read from the provider's prompt cache
    cache_write_tokens: int = 0  # written to it (Claude bills them at a premium)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tool_calls: tuple[ToolCall, ...]
    stop_reason: str  # "end", "tool_use", "max_tokens", "refusal", or the provider's own value
    usage: Usage = field(default_factory=Usage)
    raw: Any = None  # JSON-serialisable; replayed to the same provider only

    def as_message(self, provider: str) -> Message:
        message: Message = {"role": "assistant", "content": self.text, "provider": provider, "raw": self.raw}
        if self.tool_calls:
            message["tool_calls"] = [asdict(call) for call in self.tool_calls]
        return message


class LLMClient(Protocol):
    provider: str
    model: str

    def complete(self, system: str, messages: Sequence[Message], tools: Sequence[Mapping[str, Any]]) -> LLMResponse:
        """One model call. `tools` are the registry's neutral definitions (name, description, input_schema)."""
        ...


def replayable(message: Message, provider: str) -> bool:
    return message.get("provider") == provider and message.get("raw") is not None
