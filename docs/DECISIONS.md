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
| Gemini (free tier) | `gemini-3.8-flash`, run 1 | PASS | PASS | 32.47 s, 102.35 s | 454 / 75 |
| Gemini (free tier) | `gemini-3.8-flash`, run 2 | FAIL: HTTP 503 after the SDK's 2 retries | | | |
| Gemini (free tier) | `gemini-3.5-flash-lite` | PASS | PASS | 1.20 s, 0.68 s (no retries) | 311 / 48 |
| Claude | `claude-haiku-5-5` | not run: no Anthropic API credit available on 2026-10-31 | | | |

- **Answer to the key question:** the Gemini free tier accepts tool calling through the OpenAI-compatible endpoint,
  including the second request that sends the tool result back (the assistant message is returned as received, which
  keeps any thought signature).
- **Gemini models (approved by Vinicius):** both `gemini-3.8-flash` and `gemini-3.5-flash-lite` go into the evaluation
  as candidates, and the selection rule in the plan (section 9) decides; the smoke test only proves the protocol, not
  quality. `gemini-3.8-flash` worked once, but with 32 s and 102 s per call, and then failed with 503 (two runs only,
  so an observation, not a measurement); Flash-Lite answered in about 1 s without retries. Consequences for the eval
  runner: retry 429/503 with backoff, cache finished cases, and report each model's error rate next to its accuracy.
  A model that cannot finish the golden set on the free tier is reported as such. Free-tier latency is not a proxy for
  paid-tier latency, and the README must say so.
- **Free-tier limits of this project (Google AI Studio, read on 2026-10-31):**

  | Model | Requests per minute | Input tokens per minute | Requests per day |
  |---|---:|---:|---:|
  | `gemini-3.8-flash` | 5 | about 250K | 20 |
  | `gemini-3.5-flash-lite` | 15 | about 250K | 500 |

  Token limits are not a concern (a request is a few thousand tokens). The binding limits are 5 RPM and **20 RPD** on
  `gemini-3.8-flash`: a full golden-set run (about 20 cases, 2 to 3 calls each) does not fit in one day, and SDK retries
  count against the quota. Consequences: development uses Ollama and Flash-Lite only, so 3.8 Flash quota is kept for the
  evaluation; the runner throttles per model (at least 12 s between calls for 3.8 Flash, 4 s for Flash-Lite) and caps
  retries. Whether 3.8 Flash runs the full set across days or a fixed subset is decided in phase 5, once the real number
  of calls per case is known. The 503 seen in the smoke test happened at 3 RPM and about 5 requests that day, so it was
  not our quota.
- **Claude:** `python scripts/smoke_test.py claude` is ready to run once there is credit. Until then Claude stays out of
  the quality comparison and appears in the cost projection only (plan, section 9).
- **Note for phase 2:** Qwen wrote the price as "R$ 1234.56" (English decimal separator), while both Gemini models wrote
  "R$ 1.234,56". Tools should return a formatted BRL string next to the number, so the model does not have to format
  money.

## D-004: Data access layer

- **Status:** approved by Vinicius on 2026-11-01.
- **Context:** the store data is small and static: 65 products, 9 categories, 50 customers, 20 orders, 22 order items
  and 25 promotions, read by a single CLI process. The brief asks for the simplest solution; Vinicius also wants a
  design that can grow later without a rewrite.
- **Options:** (A) SQLite in memory with SQL inside the tools (the plan's first proposal); (B) in-memory Python objects
  behind a small repository interface; (C) pandas DataFrames; (D) SQLAlchemy ORM over SQLite.
- **Choice:** B. Frozen dataclasses (`data/models.py`) built from the cleaned CSVs (`data/loader.py`) and held by
  `InMemoryStore` (`data/memory.py`), which implements `StoreRepository` (`data/repository.py`). Tools receive a
  `StoreRepository` and only call its methods; they never read CSVs or raw collections. The interface grows one method
  at a time, as each tool needs it.
- **Why:** at this size a database adds code without any gain in speed or safety. Money stays in `Decimal` from the CSV
  to the tool result (Pix discount, installments), where SQLite would need integer cents and conversions both ways.
  Evolution comes from the seam: a `SqlStore` implementing the same interface (SQLite or Postgres) replaces
  `InMemoryStore` without touching tools or agent, and the same contract tests run against both.
- **When to switch to a database:** the data grows to thousands of rows, changes during a session, or is shared by
  several processes.
- **Rejected:** pandas (heavy dependency, no path to a database); SQLAlchemy (dependency and boilerplate for about 200
  rows); a free-form SQL agent (unsafe with customer data, see `PLAN.md`, section 4).
