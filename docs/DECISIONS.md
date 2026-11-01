# Decision log

Each decision with its context, the options considered, the choice and the reason. Vinicius approves every decision; the
**Status** line says whether an entry is approved or still a proposal. Architecture proposals not yet discussed live in
`docs/PLAN.md`.

## D-001: Python tooling

- **Status:** proposed in phase 0, awaiting approval.
- **Context:** the brief requires Python; the repository must run from a clean clone on a second machine.
- **Options:** pip with `pyproject.toml`; uv; Poetry.
- **Choice:** Python 3.13 (3.12 also supported), a `.venv` created with `python -m venv`, dependencies declared in
  `pyproject.toml` (setuptools, `src/` layout, `pytest` as the `dev` extra) and installed with `pip install -e ".[dev]"`.
- **Why:** nothing to install beyond Python itself, and every reviewer knows the commands. Each dependency carries its
  reason as a comment in `pyproject.toml`.

## D-002: Store data kept byte for byte

- **Status:** proposed in phase 0, awaiting approval.
- **Context:** the CSVs use CRLF line endings. Git for Windows ships with `core.autocrlf=true`, which would store them
  with LF, so a clone would not be identical to the files received.
- **Options:** accept the normalisation; mark `data/` as binary-like in `.gitattributes`.
- **Choice:** `.gitattributes` sets `data/** -text`.
- **Why:** the rule "raw files are never edited" covers line endings too. The SHA-256 of each file is recorded in
  `docs/DATA_NOTES.md`, so anyone can check the clone against the originals.

## D-003: Provider smoke test (phase 0)

- **Status:** record of results; the candidate list itself is the plan's (section 9).
- **Context:** the plan compares Claude, Gemini (free tier) and a local Qwen through Ollama. Before building on any of
  them we need to know that each one accepts tool calling through the SDK we intend to use.
- **Test:** `scripts/smoke_test.py` runs one tool-calling round trip per provider: a customer question with one
  strict-schema tool, the model must call the tool with the product name, receive a canned result and answer in text.
- **Models tested:**
  - Claude: `claude-haiku-5-5`, official `anthropic` SDK 2.3.0 (API version `2026-10-21`), effort `low`, no sampling
    parameters.
  - Gemini: `gemini-3.8-flash` through `https://generativelanguage.googleapis.com/v1beta/openai/` with the `openai` SDK.
    It is free of charge on the free tier and is the model the OpenAI-compatibility guide uses (Google pricing page,
    updated 2026-10-30). Other free-tier options: `gemini-3.5-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`.
  - Ollama: `qwen2.5:7b-instruct-q4_K_M` (the local tag of `qwen2.5:7b`, same digest) at `http://localhost:11434/v1`.
- **Results (2026-10-31, laptop):**

| Provider | Model | Tool call | Final answer | Latency (call 1, call 2) | Tokens in / out |
|---|---|---|---|---|---|
| Ollama | `qwen2.5:7b-instruct-q4_K_M` | PASS | PASS | 2.86 s, 0.45 s (15.8 s on a cold start) | 479 / 50 |
| Claude | `claude-haiku-5-5` | pending (`.env` not created yet) | | | |
| Gemini | `gemini-3.8-flash` | pending (`.env` not created yet) | | | |

- **Note for phase 2:** Qwen wrote the price as "R$ 1234.56" (English decimal separator). Tools should return a
  formatted BRL string next to the number, so the model does not have to format money.
