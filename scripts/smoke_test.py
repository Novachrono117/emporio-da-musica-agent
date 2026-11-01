"""Phase 0 smoke test: one tool-calling round trip per LLM provider.

For each provider the script sends a customer question with one tool available, checks that the model calls the tool
with a sensible argument, sends back a canned tool result and checks that the model then answers in text.
API keys are read from .env and never printed.

Usage:
    python scripts/smoke_test.py                 # all providers
    python scripts/smoke_test.py ollama gemini   # a subset
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODELS = {"claude": "claude-haiku-5-5", "gemini": "gemini-3.8-flash", "ollama": "qwen2.5:7b-instruct-q4_K_M"}

SYSTEM = (
    "Você é o assistente da loja Empório da Música. Para informar preços, use sempre a ferramenta "
    "get_product_price; nunca invente valores."
)
QUESTION = "Quanto custa o violão Takamine GD20?"
TOOL_NAME = "get_product_price"
TOOL_DESCRIPTION = "Returns the current price of a product sold by the store."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {"product_name": {"type": "string", "description": "Product name as the customer wrote it."}},
    "required": ["product_name"],
    "additionalProperties": False,
}
# Canned result: this test checks the tool-calling protocol, not the store data.
TOOL_RESULT = {"product_name": "Violão Takamine GD20", "price_brl": 1234.56, "source": "smoke-test fixture"}
PRICE_DIGITS = "123456"


@dataclass
class Outcome:
    provider: str
    model: str
    status: str = "FAIL"  # PASS, FAIL or SKIPPED
    tool_args: dict | None = None
    answer: str = ""
    latency_s: list[float] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    note: str = ""

    def judge(self) -> None:
        called_right_tool = self.tool_args is not None and "takamine" in json.dumps(self.tool_args).lower()
        self.status = "PASS" if called_right_tool and self.answer.strip() else "FAIL"
        if self.status == "PASS" and PRICE_DIGITS not in re.sub(r"\D", "", self.answer):
            self.note = "answer does not quote the tool's price"


def _timed(outcome: Outcome, call):
    start = time.perf_counter()
    result = call()
    outcome.latency_s.append(round(time.perf_counter() - start, 2))
    return result


def run_claude(model: str, api_key: str) -> Outcome:
    import anthropic

    outcome = Outcome("claude", model)
    client = anthropic.Anthropic(api_key=api_key)
    tools = [{"name": TOOL_NAME, "description": TOOL_DESCRIPTION, "input_schema": TOOL_SCHEMA, "strict": True}]
    # No temperature/top_p/top_k: the API rejects them. Low effort suits a chat route.
    request = {"model": model, "max_tokens": 1024, "system": SYSTEM, "tools": tools, "output_config": {"effort": "low"}}
    messages = [{"role": "user", "content": QUESTION}]

    first = _timed(outcome, lambda: client.messages.create(messages=messages, **request))
    outcome.input_tokens += first.usage.input_tokens
    outcome.output_tokens += first.usage.output_tokens
    calls = [block for block in first.content if block.type == "tool_use"]
    if not calls:
        outcome.note = f"no tool call (stop_reason={first.stop_reason})"
        return outcome
    outcome.tool_args = calls[0].input

    # The assistant turn goes back unchanged (thinking blocks included), followed by one result per call.
    messages.append({"role": "assistant", "content": first.content})
    results = [{"type": "tool_result", "tool_use_id": call.id, "content": json.dumps(TOOL_RESULT)} for call in calls]
    messages.append({"role": "user", "content": results})

    second = _timed(outcome, lambda: client.messages.create(messages=messages, **request))
    outcome.input_tokens += second.usage.input_tokens
    outcome.output_tokens += second.usage.output_tokens
    outcome.answer = "".join(block.text for block in second.content if block.type == "text")
    outcome.judge()
    return outcome


def run_openai_compat(provider: str, model: str, base_url: str, api_key: str) -> Outcome:
    from openai import OpenAI

    outcome = Outcome(provider, model)
    client = OpenAI(api_key=api_key, base_url=base_url)
    tools = [{"type": "function", "function": {"name": TOOL_NAME, "description": TOOL_DESCRIPTION, "parameters": TOOL_SCHEMA}}]
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": QUESTION}]

    def create():
        return client.chat.completions.create(model=model, messages=messages, tools=tools, tool_choice="auto")

    first = _timed(outcome, create)
    _add_openai_usage(outcome, first)
    message = first.choices[0].message
    if not message.tool_calls:
        outcome.note = f"no tool call (finish_reason={first.choices[0].finish_reason})"
        return outcome
    outcome.tool_args = json.loads(message.tool_calls[0].function.arguments)

    # model_dump keeps provider-specific extras on the tool calls (for example Gemini thought signatures).
    messages.append(message.model_dump(exclude_none=True))
    for call in message.tool_calls:
        messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(TOOL_RESULT)})

    second = _timed(outcome, create)
    _add_openai_usage(outcome, second)
    outcome.answer = second.choices[0].message.content or ""
    outcome.judge()
    return outcome


def _add_openai_usage(outcome: Outcome, response) -> None:
    if response.usage:
        outcome.input_tokens += response.usage.prompt_tokens or 0
        outcome.output_tokens += response.usage.completion_tokens or 0


def run(provider: str, model: str) -> Outcome:
    if provider == "claude":
        key = os.getenv("ANTHROPIC_API_KEY", "")
        return run_claude(model, key) if key else Outcome(provider, model, "SKIPPED", note="ANTHROPIC_API_KEY not set")
    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            return Outcome(provider, model, "SKIPPED", note="GEMINI_API_KEY not set")
        return run_openai_compat(provider, model, GEMINI_BASE_URL, key)
    base_url = os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL
    return run_openai_compat(provider, model, base_url, "ollama")  # Ollama ignores the key, the SDK requires one


def _redact(text: str) -> str:
    for name in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        secret = os.getenv(name)
        if secret:
            text = text.replace(secret, "***")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("providers", nargs="*", help=f"any of {', '.join(DEFAULT_MODELS)} (default: all)")
    for provider, model in DEFAULT_MODELS.items():
        parser.add_argument(f"--{provider}-model", default=model)
    args = parser.parse_args()
    unknown = set(args.providers) - set(DEFAULT_MODELS)
    if unknown:
        parser.error(f"unknown provider(s): {', '.join(sorted(unknown))}")
    args.providers = args.providers or list(DEFAULT_MODELS)

    sys.stdout.reconfigure(encoding="utf-8")
    if not (ROOT / ".env").exists():
        print("No .env file: copy .env.example to .env and fill in the keys you have.")
    load_dotenv(ROOT / ".env")

    outcomes = []
    for provider in args.providers:
        model = getattr(args, f"{provider}_model")
        try:
            outcome = run(provider, model)
        except Exception as error:  # report every provider, even when one fails
            outcome = Outcome(provider, model, note=_redact(f"{type(error).__name__}: {error}")[:400])
        outcomes.append(outcome)
        print(f"\n[{outcome.status}] {provider} / {model}")
        print(f"  tool args : {json.dumps(outcome.tool_args, ensure_ascii=False)}")
        print(f"  answer    : {outcome.answer.strip()[:300]}")
        print(f"  latency s : {outcome.latency_s}")
        print(f"  tokens    : in={outcome.input_tokens} out={outcome.output_tokens}")
        if outcome.note:
            print(f"  note      : {outcome.note}")

    print("\nSummary: " + ", ".join(f"{o.provider}={o.status}" for o in outcomes))
    return 1 if any(o.status == "FAIL" for o in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())
