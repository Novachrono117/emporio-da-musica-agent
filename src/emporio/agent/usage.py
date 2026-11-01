"""Usage log: one JSON line per model call in logs/usage.jsonl, kept out of git (decision D-008).

It records tokens, latency and the names of the tools called, never the conversation text (LGPD). The evaluation
(phase 5) and the cost projection (phase 6) read it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from emporio.llm.base import LLMResponse

USAGE_PATH = Path(__file__).resolve().parents[3] / "logs" / "usage.jsonl"


class UsageLog:
    def __init__(self, path: Path = USAGE_PATH) -> None:
        self.path = path

    def record(self, session_id: str, provider: str, model: str, response: LLMResponse, latency_s: float) -> None:
        entry: dict[str, Any] = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "session_id": session_id,
            "provider": provider,
            "model": model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cached_input_tokens": response.usage.cached_input_tokens,
            "cache_write_tokens": response.usage.cache_write_tokens,
            "latency_s": round(latency_s, 3),
            "stop_reason": response.stop_reason,
            "tools": [call.name for call in response.tool_calls],
        }
        self._append(entry)

    def event(self, session_id: str, name: str, **details: Any) -> None:
        """A guard firing, for example (D-009); details hold amounts or flags, never conversation text."""
        self._append(
            {
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "session_id": session_id,
                "event": name,
                **details,
            }
        )

    def _append(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
