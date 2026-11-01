"""Guards on .env.example: it lists every setting and never carries a value."""

from pathlib import Path

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
EXPECTED = {"ANTHROPIC_API_KEY", "GEMINI_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "OLLAMA_BASE_URL", "EMPORIO_TODAY"}


def _entries() -> dict[str, str]:
    entries = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, _, value = line.partition("=")
            entries[name.strip()] = value.strip()
    return entries


def test_env_example_lists_every_setting():
    assert set(_entries()) == EXPECTED


def test_env_example_has_no_values():
    # Report variable names only: the values may be real keys.
    filled = sorted(name for name, value in _entries().items() if value)
    assert not filled, f".env.example must not carry values; clear: {', '.join(filled)}"
