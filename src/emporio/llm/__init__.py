"""LLM providers behind one interface (decision D-008): Claude, Gemini and Ollama."""

from __future__ import annotations

import os

from emporio.llm.base import LLMClient, LLMError

PROVIDERS = ("ollama", "gemini", "anthropic")
# The evaluation made Gemini 3.5 Flash-Lite the default by rule 4: the highest pass rate, below the bar (D-010,
# docs/EVAL.md). Ollama runs the best local model that fits an 8 GB GPU, Qwen 3.5 4B; it needs the Ollama server
# started with an 8k context (README). Haiku is the Claude candidate.
DEFAULT_PROVIDER = "gemini"
DEFAULT_MODELS = {
    "ollama": "qwen3.5:4b",
    "gemini": "gemini-3.5-flash-lite",
    "anthropic": "claude-haiku-5-5",
}
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY")


def create_client(provider: str, model: str | None = None) -> LLMClient:
    """A client for the provider, with keys read from the environment (.env); never pass a key around."""
    if provider not in PROVIDERS:
        raise LLMError(f"unknown provider {provider!r}; use one of: {', '.join(PROVIDERS)}")
    model = model or DEFAULT_MODELS[provider]
    if provider == "anthropic":
        from emporio.llm.anthropic_client import AnthropicClient

        _require("ANTHROPIC_API_KEY")
        return AnthropicClient(model)

    from emporio.llm.openai_compat_client import OpenAICompatClient

    if provider == "gemini":
        return OpenAICompatClient("gemini", model, GEMINI_BASE_URL, _require("GEMINI_API_KEY"))
    base_url = os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL
    return OpenAICompatClient("ollama", model, base_url, "ollama")  # Ollama ignores the key; the SDK needs one


def redact(text: str) -> str:
    """Remove any API key from a message before it is printed or logged."""
    for name in _KEYS:
        secret = os.getenv(name)
        if secret:
            text = text.replace(secret, "***")
    return text


def _require(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise LLMError(f"{name} is not set: add it to .env (see .env.example)")
    return value
