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

## Phase 1: data

- **Asked:** load and clean the store data and the policy manual, with the simplest design that can still grow later.
- **Produced by Claude Code:**
  - the data access proposal (D-004), comparing in-memory records, SQLite, pandas and SQLAlchemy;
  - typed models, a loader that validates the CSVs and refuses broken data, the `StoreRepository` interface and its
    `InMemoryStore`, the policy manual split into 29 sections, and the agent's "today" in store time;
  - a profile of every CSV (`docs/DATA_NOTES.md`) and 36 tests;
  - a review of every business rule against consumer law, data protection law and the Gemini terms (D-005).
  A Claude Code session on the second machine wrote the first read of the manual and the orders; the laptop session
  re-checked every number in it against the CSVs and the PDF.
- **Reviewed or changed by Vinicius:**
  - asked for a design that is simple now and can scale later, which shaped D-004's repository seam; he asked whether
    it was really the best option before approving it;
  - asked whether store time should be Brasília's; it stays UTC-4 (Campo Grande), checked against the time zone data;
  - pointed out that the consumer code gives 7 days of regret from receipt, then asked for every proposal to be checked
    against external rules. That review changed seven rules (installment display, contacts, warranty, regret, last
    units, order lookup, catalog gaps) and added four (LGPD and the Gemini free tier, binding offers, virtual assistant
    disclosure, complaint deadline).
- **Caught by tests:** a test assumed the wrong price for product 81; it was corrected against the CSV.

## Phase 2: tools

- **Asked:** build the tools of the plan (section 7), following the business rules approved in D-005.
- **Produced by Claude Code:**
  - a proposal (D-006) after checking the plan's seven tools against D-005: the rules needed date arithmetic for
    returns and warranty, a record of regret requests and contact data that resolves the manual's conflicts, none of
    which the plan covered; the proposal also checked which JSON Schema keywords Claude's strict tool use accepts;
  - eight tools with hand-written schemas, a small validator, company data and hours checked against the manual's
    text, a local ticket log kept out of git, and 159 tests;
  - one request per provider with all eight schemas: Ollama (Qwen 2.5 7B) and Gemini Flash-Lite both accepted them.
    Gemini searched before quoting; Qwen called `quote_payment` with product ids it made up, so the tool description
    now says where ids come from, and phases 3 and 4 have to handle it.
- **Reviewed or changed by Vinicius:** asked whether the proposal was really the most adequate plan. Re-checking it
  changed two points before he approved it: `quote_payment` takes the cart items instead of a free amount (the model
  never adds up prices or quotes an invented value), and `check_return_options` says "within the deadline" with the
  conditions a person checks, instead of "eligible", which would bind the store.
- **Found in the data:** product 130 is coming soon but appears in two orders, and seven products between 135 and
  144 have descriptions that name another brand or model (`docs/DATA_NOTES.md`). Vinicius chose to drop those
  descriptions rather than keep them with a warning (D-007).
- **Caught before running:** two phone endings in the first draft of the order tests were wrong; they were corrected
  against the CSV.
