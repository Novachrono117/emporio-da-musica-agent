# How coding assistants were used

The brief allows coding assistants as long as the README explains how. This log records, phase by phase, what was asked,
what the assistant (Claude Code) produced, and what Vinicius reviewed or changed. It becomes the README section on
coding assistants.

Working agreement (see `CLAUDE.md`): Vinicius owns the architecture and approves every decision; Claude Code proposes,
implements one phase at a time and writes the tests; every commit made with Claude Code carries a `Co-Authored-By`
trailer.

## Phase 0: setup

- **Asked:** initialise the repository, extract the store data exactly as provided, create `pyproject.toml`, `.venv`,
  `.env.example` and the docs stubs, and run one tool-calling smoke test per provider (Claude, Gemini free tier, Ollama).
- **Produced by Claude Code:**
  - repository skeleton (`pyproject.toml`, `.env.example`, `.gitattributes`, `src/emporio/`), a test that keeps
    `.env.example` complete and free of values;
  - `data/` extracted from the zip, with SHA-256 hashes in `docs/DATA_NOTES.md`;
  - `scripts/smoke_test.py`, after checking the current Anthropic SDK notes for Claude Haiku 5.5 and the current Google
    docs for the Gemini OpenAI-compatible endpoint and free-tier models;
  - results in `docs/DECISIONS.md` (D-003).
- **Findings that changed the plan:** the CSVs have no BOM (the plan assumed one); the local Ollama tag is
  `qwen2.5:7b-instruct-q4_K_M`, not `qwen2.5:7b`; the Gemini free tier accepts tool calling, but `gemini-3.8-flash`
  was slow and then returned 503, while `gemini-3.5-flash-lite` answered in about 1 s.
- **Done by Vinicius:** approved creating the private GitHub repository; created the `.env` keys himself (they never
  went through the chat). Claude was not tested because there is no API credit available at the moment.
- **Reviewed or changed by Vinicius:** pending.
