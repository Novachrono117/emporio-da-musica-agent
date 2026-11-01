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

## Phase 3: agent

- **Asked:** the LLM interface, an adapter for Claude and one for Gemini and Ollama, the tool-calling loop, saved
  sessions and the CLI; done when the loop passes tests with a scripted LLM and a real conversation runs on the local
  model.
- **Produced by Claude Code:**
  - a plan with five open points (D-008), after reading the current Anthropic docs: Claude Haiku 5.5 thinks
    adaptively by default and its thinking blocks must go back unchanged with the tool results; prompt caching is a
    prefix match, so the system prompt carries the store date but not the time of day;
  - the interface and both adapters, tested against real SDK response objects without network calls; the loop with
    its fixed answer at the tool cap; sessions that keep the tools' state; a usage log without conversation text; the
    product id guard; the CLI (`python -m emporio`); 189 tests;
  - real conversations with the same three questions (a price, installments, order 8 with its phone ending) on
    Qwen 2.5 7B through Ollama and on Gemini Flash-Lite. Both called the right tools with the right arguments, and
    Gemini's second turn replayed its thought signatures.
- **Reviewed or changed by Vinicius:** read the plan and approved it, including the product id guard proposed after
  the phase 2 schema check.
- **Found while building:** the current SDKs depend on `httpx2`, not `httpx` (a test that built SDK errors was
  adjusted); new sessions were named after the simulated store date, and now use the real clock.
- **For phase 4, from the real conversations:** Qwen offered a shopping cart the store does not have, wrote an
  English word in a Portuguese answer and sent the customer to the carrier about a late delivery instead of offering
  a person; Gemini offered a person, but used Markdown bold, which a terminal or WhatsApp shows as asterisks, and
  offered to place the order, which the agent cannot do.

## Phase 4: behaviour

- **Asked:** the persona, guardrails and out-of-scope handling, tested on the brief's four example questions. Vinicius
  asked for more test conversations than those four: "testing more is never a problem".
- **Produced by Claude Code:**
  - a plan with five points (D-009): a Portuguese prompt, a fixed greeting, plain text, an amount check in code and
    no new memory work;
  - 39 test conversations in `eval/scenarios.yaml` (the brief's four plus catalog, promotions, payment, shipping,
    orders and privacy, returns and warranty, hours, scope and prompt injection) and a runner that writes a
    transcript per model to `eval/transcripts/`;
  - the amount check: an answer that cites an amount in reais no tool returned is rewritten once, then replaced by
    the fixed answer;
  - four full runs on Qwen 2.5 7B and three on Gemini Flash-Lite, each transcript read by hand, with the changes
    below between runs. The final transcripts are in `eval/transcripts/`; the first ones are in the git history.
- **What the runs changed:**
  - the first prompt spelled out every rule, and Qwen stopped calling tools: it invented an address, opening hours
    and ticket numbers. A side-by-side run of the phase 3 prompt and the long one on five scenarios showed the
    length was the cause. The prompt became shorter and tool-first, with a table that routes each kind of question
    to its tool, and the situational rules moved into the tool results;
  - the prompt now says whether the store is open and when it opens, without the clock time, so it stays cacheable;
  - a search for an accessory returns only the note (listing seven-string guitars for "cordas" read as a yes);
  - a product asked by name that is out of stock or coming soon is reported with its status instead of "not found"
    (Gemini had told a customer the store did not have the Giannini GF-3D);
  - a late order tells the agent to apologise and offer a person; a repeated identical order lookup no longer uses
    up the customer's attempts (Gemini sent the same wrong pair three times in one turn);
  - the prompt tells the model to say when a tool did not return a detail (Gemini called the C40 top "laminated")
    and that the store sells no accessories.
- **Reviewed or changed by Vinicius:** approved D-009 and asked for a broader test battery than the brief's examples,
  which is what exposed the long prompt's effect on the small model.
- **Outcome by model:** Gemini Flash-Lite handled the scenarios well from the first run (right tools, no invented
  amount, no Markdown); it still describes the C40 top as laminated, from its own knowledge of the real guitar, since
  the data does not say. Qwen 2.5 7B improved with the shorter prompt but stays unreliable from run to run: tool calls
  written as text, answers drifting into Chinese or Russian, invented contacts, and once the card price given as the
  Pix price. The amount check cannot catch that last case, because the amount did come from a tool. Measuring all
  this is phase 5's job.
- **Ollama context:** Ollama gives a 4,096-token context on GPUs under 24 GB, and its OpenAI-compatible API cannot
  change it (a Modelfile or `OLLAMA_CONTEXT_LENGTH` can). The runs stayed under 3,000 input tokens, so nothing was
  cut, but long conversations will reach the limit; the README must say how to raise it.

## Phase 5: evaluation

- **Asked:** evaluate the candidate models on a golden set with deterministic grading and pick the default with a
  rule written before running.
- **Produced by Claude Code:**
  - the evaluation design and selection rule (D-010), committed before any evaluation run, with a fallback for when
    no model meets the bar;
  - expectations for the 39 scenarios (tools, facts, behaviour, forbidden content), checked against the tools' own
    output by a test; a runner that grades, resumes after a spent quota and writes `docs/EVAL.md`;
  - the choice of the second machine's model (`qwen3.5:9b-q4_K_M`, 6.6 GB for a 10 GB GPU) from the current Ollama
    library, with step-by-step instructions for running it there.
- **Found by reading the results:**
  - after the first run, behaviour phrases were being counted as facts, and two grader bugs ("°C" folded to "c"; a
    colloquial refusal rejected). They were fixed and every stored answer regraded (D-010); no answer was rerun or
    edited;
  - the first Qwen 3.5 4B runs were cut by Ollama's default 4k context, and one of them invented a WhatsApp number
    that is a customer's phone, which disqualified the model. The runs were discarded and rerun with an 8k context
    (D-010, local models);
  - after the last run, two expectations rejected right answers ("a gente não tem saxofone"; an out-of-stock answer
    that began "não temos esse modelo exato"). They were fixed and every answer regraded; three scenario runs went
    from fail to pass and no verdict changed (D-010);
  - in one Flash-Lite run the agent told a customer the order checks were over after two failures, then checked the
    right pair and showed the order. The code had kept its rule; a hand-off for failed verification now locks the
    lookup as well (D-006). The runs were made before this change.
- **Reviewed or changed by Vinicius:** approved the plan, the three runs per model and the selection rule; ran the 9B
  model and two of the Flash-Lite runs on his desktop; approved the lockout change and the two expectation fixes.
- **Result (`docs/EVAL.md`):** no model met rule 2. Gemini 3.5 Flash-Lite had the highest pass rate (93% over three
  runs, every expected tool, 98% of the facts, no leak and no invented amount) and is the default by rule 4, which the
  README must say. Qwen 3.5 9B reached 64% and the 4B 62%, both with Markdown in about a quarter of the runs; Qwen 2.5
  7B 44%; Gemini 3.8 Flash is partial (HTTP 503, 30 to 230 s per call). Without options the CLI now uses Flash-Lite.

## Phase 6: examples and costs

- **Asked:** 3 to 5 example conversations, at least one non-trivial, and a cost projection from measured tokens with
  dated prices.
- **Produced by Claude Code:**
  - the plan (D-011), approved before any work;
  - five example conversations in `examples/`, each from a single run of the default model with the final code,
    written with their tool calls and results by `scripts/run_examples.py`, and an index that says what went wrong
    in them (a hand-off with the wrong reason; a regret request recorded one message early);
  - `scripts/cost_report.py` and `scripts/pricing.yaml`, with prices read from the official pages, the PTAX rate
    from the Banco Central API and a GPU machine from Azure's retail prices API, and the generated `docs/COSTS.md`.
- **Found while building:** Gemini's OpenAI-compatible endpoint leaves thinking out of `completion_tokens`. Two
  calls showed it, the adapter now counts thinking as output, and 8 calls of the agent showed no thinking at the
  default level, so the evaluation's tokens stand (D-011).
- **Reviewed or changed by Vinicius:** approved D-011, including keeping wrong answers in the examples with a note.
- **Result:** at 100 conversations a day the default model costs about US$ 7.44 (R$ 40,34) a month; Claude Haiku
  5.5, projected, US$ 2.57, or US$ 1.65 with prompt caching; a rented T4 machine costs US$ 652.62 a month and pays
  for itself only above about 8,770 conversations a day.
