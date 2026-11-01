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
  money. (Superseded by D-006, choice 5: formatted text only.)

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

## D-005: Business rules from the data, the manual and the law

- **Status:** approved by Vinicius on 2026-11-01, after each rule was checked against Brazilian consumer law and the
  providers' terms (sources below). The rules drive the tools (phase 2) and the system prompt (phase 4). Where the
  "Proposed" lines in `docs/DATA_NOTES.md` differ, this entry wins.
- **Context:** the manual contradicts itself in places, the data and the manual disagree, and a few manual rules sit in
  tension with the law. The agent must never state something the store cannot honour: precise information given to a
  customer binds the store (CDC, arts. 30 and 35). This is also why prices, stock and promotions only ever come from a
  tool result.
- **Rules:**
  1. **Manual text:** read with pypdf's layout mode, page headers and footers dropped, split into its 29 numbered
     sections. Contradictions are kept as written and resolved by the rules below.
  2. **Installments:** section 3.1 wins over the summary table in section 3: each installment is at least R$ 50 up to
     3x, R$ 80 from 4x to 6x and R$ 100 from 7x to 12x, with no interest; combined payment methods only above
     R$ 2,000. Every quote shows the cash price, the total, "N x R$ X sem juros" and the Pix price (Decreto
     5.903/2006, art. 3; Lei 13.455/2017). Installments add up to the total exactly; the last one absorbs the cents.
     The 5% Pix discount never applies to a promotional price (6.2).
  3. **Contacts:** e-mail `contato@emporiodamusica.com.br` (on the cover; the accented form in 1.2 may be a valid .br
     domain, but plain ASCII works in every mail client); phone (67) 3341-4444; WhatsApp (67) 3321-4500 (section 7,
     the section dedicated to the channel wins over the summary table, as in rule 2). Company name, CNPJ and address
     come from 1.2 (Decreto 7.962/2013, art. 2). The README lists the conflicts.
  4. **Defects and warranty:** up to 30 days after the purchase, exchange at the store (4.2). After that the agent never
     denies the warranty and never sends the customer to the manufacturer: store and manufacturer answer jointly for
     defects (CDC, art. 18), the legal warranty runs 90 days from receipt (8.1; CDC, art. 26) or, for a hidden defect,
     from when it shows up (art. 26, §3), and the manufacturer's warranty adds to it (8.2; art. 50). The agent explains
     this and hands off to a human; the store can intermediate (4.2). The README records the tension between 4.2 and
     the CDC.
  5. **Regret (4.1):** only for purchases made outside the store (online, phone), within 7 calendar days of receipt
     (CDC, art. 49). The agent asks how and when the customer received the product instead of inferring it, records
     the request and confirms receipt at once (Decreto 7.962/2013, art. 5). In-store purchases have no regret right but
     do have the 7-day preference exchange (4.3). The manual refunds within 10 business days while the law says
     "immediately": the agent states the store policy and the README records the tension.
  6. **Accessories:** redirected politely, without naming another store (7.1).
  7. **Today:** `EMPORIO_TODAY` defaults to 2026-03-23, the day after the last order; the time of day comes from the
     real clock in store time, UTC-4 (Campo Grande, no daylight saving time since 2019, while Brasília is UTC-3); a
     full date and time fixes both for tests and the evaluation. Holidays are not computed (known limitation).
  8. **Past order totals:** shown as recorded and never recomputed; the agent does not guess why a total differs from
     its items (orders 3 and 20).
  9. **Past installments:** shown as recorded; the installment rules apply to new quotes only (orders 9, 16 and 18).
  10. **Availability:** active with stock is available; active without stock is out of stock, with similar
      alternatives (7.3); discontinued with stock sells as last units, "while stock lasts, no reservation" (6.2;
      Decreto 7.962/2013, art. 2, VI); discontinued without stock is no longer sold, with equivalents (7.3); coming
      soon is not on sale, with no price or date promised, even when it has stock.
  11. **Order lookup (LGPD, arts. 6 and 46):** needs the order number **and** the last 4 digits of the customer's
      phone. The check runs in code and the model never sees the phone. Every failure gets the same neutral message;
      after 3 failed attempts in a session the agent hands off to a human. The result carries only what the customer
      needs (no phone, no e-mail). Customers are never identified by e-mail: two of them share one.
  12. **Catalog gaps:** availability comes from the data, never from the manual's description of the catalog (chapter 1
      mentions wind and orchestral instruments; categories 6 to 8 have no products). No restocking is promised.
  13. **Data sent to LLM providers:** the Gemini free tier may use prompts to improve Google products, lets human
      reviewers read them, and its terms ask not to send personal information. That is acceptable for this fictional
      dataset only: the README states that real customer data needs a paid tier under a data processing agreement, and
      the cost projection prices paid tiers. Files with conversations stay out of git.
  14. **Virtual assistant:** the agent introduces itself as the store's virtual assistant (CDC, art. 6, III; the manual
      mentions it in section 7). The AI bill PL 2338/2023 was still under review in the Chamber of Deputies when this
      was written.
  15. **Complaints:** the agent promises the manual's 24 business hours (7.3), stricter than the 5 days of Decreto
      7.962/2013, art. 4.
- **Sources (read on 2026-11-01):** [CDC, Lei 8.078/1990](https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm);
  [Decreto 7.962/2013](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/decreto/d7962.htm);
  [Decreto 5.903/2006](https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/decreto/d5903.htm);
  [Lei 13.455/2017](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2017/lei/l13455.htm);
  [LGPD, Lei 13.709/2018](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm);
  [Gemini API terms](https://ai.google.dev/gemini-api/terms) (updated 2026-04-28);
  [PL 2338/2023](https://www.congressonacional.leg.br/web/atividade/materias/-/materia/157233).
  This is a careful reading of the texts, not legal advice.

## D-006: Tool contracts

- **Status:** approved by Vinicius on 2026-11-01.
- **Context:** the plan's seven tools (`PLAN.md`, section 7) were written before D-005, which needs date arithmetic
  (regret, defect exchange, warranty), a record of regret requests and contact data that resolves the manual's
  conflicts. The project rule keeps all arithmetic in code, never in the model.
- **Choices:**
  1. **Schemas and validation:** each tool declares a hand-written JSON Schema that uses only what Claude's strict tool
     use accepts: types, `enum`, `required` and `additionalProperties: false`. Strict mode rejects `minimum`, `maximum`
     and `minLength`, so ranges and cross-field rules are checked in code. Invalid input comes back as a structured
     error the model can read and correct. No new dependency. Rejected: pydantic (already installed with both SDKs),
     whose generated schemas carry titles, `anyOf` with null and numeric bounds that would have to be stripped for
     strict mode and are noisier for a small local model.
  2. **`quote_payment` takes items** (`product_id` and quantity), not a free amount: the code adds up the cart and
     applies promotions, the Pix discount and the installment rules, so the model can never quote an invented value.
     For combined payment methods the quote only says whether they are allowed (above R$ 2,000); the split goes to a
     person, because the manual does not say how the Pix discount applies to part of a payment. Shipping inside the
     Campo Grande metro area (free above R$ 500, otherwise R$ 35, section 5.1) is computed in the quote; other cities
     depend on data the store does not give us.
  3. **New tool `check_return_options`** (reason, purchase channel, purchase date, receipt date): deadlines are computed
     in code. It reports whether the request is within the deadline, the deadline, the days left, the conditions a
     person must check and the next step. It never says "eligible": packaging, use and misuse are checked by a person,
     and information given to a customer binds the store (CDC, art. 30). Days are counted excluding the first day and
     including the last (Código Civil, art. 132): a product received on the 16th can be returned until the 23rd. The
     7 days of the preference exchange (4.3) count from receipt, which for an in-store purchase is the purchase day
     (the manual does not say).
  4. **`handoff_to_human` records a ticket.** Its reason comes from a fixed list (customer request, regret request,
     warranty claim, policy question, failed order verification, other), which records regret requests (D-005, rule 5)
     without another tool. The result carries the contacts, whether the store is open now and when it opens next
     (7.1). Tickets and complaints go to `tickets/tickets.jsonl`, kept out of git because they hold customer data.
  5. **Money only as formatted text** (`"R$ 1.234,56"`) and dates as `dd/mm/yyyy`. All arithmetic happens before, in
     `Decimal`. This replaces the phase 0 note in D-003 (number and text side by side): with text only, the model has
     nothing to reformat or recompute.
  6. **`get_store_policy`** returns the manual sections of a topic plus notes where D-005 resolves a conflict (for
     example, the section 3 table against 3.1, or 4.2 sending the customer to the manufacturer). Contact data comes
     from D-005, not from the manual's text. Text the model reads never cites this log, only manual sections and the
     law, which the agent may quote to a customer.
  7. **Failed order lookups** are counted per session in code; at the third failure the tool stops checking and tells
     the agent to hand off. Known limitation, for the README: a new session starts the count again.
- **Changed after the evaluation (2026-11-01, approved by Vinicius):** in run 3 of Gemini Flash-Lite (`order_lockout`)
  the agent handed off after two failed lookups and told the customer the checks were over, skipped the third
  attempt, then checked the fourth, which was the right pair, and showed the order. The code kept its rule (only two
  lookups had failed, and the right pair verifies by design), but the agent announced a lock the code did not hold. A
  hand-off with reason `order_verification_failed` now locks the lookup too, if at least one lookup failed in the
  session: models also pick that reason for a late delivery the customer was verified for (phase 4 transcript, and
  run 3 of `order_late_delivery`). The evaluation runs were made before this change.
- **Tools (eight):** `search_products`, `get_product_details`, `get_order_status`, `quote_payment`,
  `check_return_options`, `get_store_policy`, `register_complaint`, `handoff_to_human`.
- **Interpretation (rule 10):** products that are not for sale (coming soon, or discontinued with no stock) are shown
  without a price, so the agent cannot quote them.

## D-007: Product descriptions that contradict the product

- **Status:** approved by Vinicius on 2026-11-01.
- **Context:** in seven products (135, 136, 137, 139, 140, 142 and 144) the description names another brand or model
  than the product's name, and some contradict the specs too: 142 is a "Korg" whose description is an 88-key Roland
  workstation, while its specs say 61 keys (`docs/DATA_NOTES.md` lists all seven). The agent would repeat whichever
  text it read, and what it tells a customer binds the store (CDC, art. 30).
- **Options:** (A) keep the descriptions and add a note telling the model to trust the name and the specs; (B) drop
  those descriptions; (C) keep everything and list the conflict as a known limitation.
- **Choice:** B. The loader drops the seven descriptions (`CONTRADICTORY_DESCRIPTIONS` in `data/loader.py`); the
  tools show the name, category, price and specs, and the search no longer matches words that only those
  descriptions held. The raw file is unchanged.
- **Why:** a small local model can ignore a note but cannot repeat a text it never sees. The cost is losing the
  descriptive text of seven products, which is the text that is wrong.

## D-008: Agent loop, sessions and LLM adapters (phase 3)

- **Status:** approved by Vinicius on 2026-11-01.
- **Context:** the plan (sections 4 and 8) fixes the shape: one LLM interface, an adapter for the Anthropic SDK and one
  for OpenAI-compatible endpoints (Gemini, Ollama), a loop with a cap of 6 tool rounds, sessions saved as JSON and a
  CLI. Five points were open.
- **Choices:**
  1. **Neutral history with an opaque block per provider.** Sessions keep one format (user, assistant with tool calls,
     tool result). Each assistant message also keeps the provider's raw response, replayed unchanged to the same
     provider only. Claude needs the assistant turn back as it came, thinking blocks included, next to the tool
     results, and editing an earlier turn invalidates them; Gemini needs its thought signatures back (D-003). With
     another provider the adapter rebuilds the message from the neutral fields. Rejected: a native history per
     provider, which would give the session store and the evaluation two formats to read.
  2. **Tool round cap:** up to 6 rounds of tool calls per customer message. If the model asks for a seventh, the
     request is dropped and the agent answers with a fixed message in Portuguese that offers a person, without calling
     the model again. The history stays valid: no tool call is left without its result.
  3. **Product id guard:** `quote_payment` accepts only product ids that `search_products` or `get_product_details`
     returned in the session; any other id is refused with a message asking for a lookup first. In the phase 2 schema
     check, Qwen 2.5 7B quoted ids it made up, one of which belonged to another product.
  4. **Usage log:** every model call appends provider, model, input, output and cached tokens, latency, the names of
     the tools called and the session id to `logs/usage.jsonl`, kept out of git. The conversation text is not logged
     (LGPD). Phases 5 and 6 read it.
  5. **No streaming in the CLI:** answers print whole, which keeps the adapters simple and the latency measurable per
     call, at the cost of a few seconds of waiting on the local model.
- **Provider settings (read in the current Anthropic docs on 2026-11-01):** Claude Haiku 5.5 uses adaptive thinking by
  default, effort `low`, `strict: true` on every tool and automatic prompt caching (top-level `cache_control`). Caching
  is a prefix match, so the system prompt carries the store date but not the time of day; tools that depend on the
  time (hours, hand-off) compute it themselves. A `refusal` stop gets the same fixed message as the cap. Gemini and
  Ollama receive the same schemas without `strict`: OpenAI's strict mode requires every property to be required, and
  the tools have optional ones; the validator checks their input.
- **Known limitation:** without API credit, the Claude adapter is tested against recorded SDK objects only, not
  against the live API.

## D-009: Agent behaviour (phase 4)

- **Status:** approved by Vinicius on 2026-11-01, who also asked for more test conversations than the brief's four.
- **Context:** the real conversations of phase 3 called the right tools, but the answers offered a shopping cart, mixed
  in an English word, sent a customer to the carrier about a late delivery, used Markdown and offered to place an
  order. The plan (section 8) lists the rules the system prompt must carry.
- **Choices:**
  1. **System prompt in Portuguese**, the customer's language, with an explicit rule to answer only in Portuguese and
     translate tool results. Tool texts stay in English (D-006); if the evaluation shows English leaking into
     answers, this is reopened.
  2. **Fixed greeting printed by the CLI** for a new session, disclosing the virtual assistant (D-005, rule 14) the
     same way every time. It is not part of the history; the prompt tells the model the customer was already greeted.
  3. **Format through the prompt only:** plain chat text, no Markdown. Code cleanup is added only if the evaluation
     shows Markdown persisting.
  4. **Amount check in code:** every amount in reais in an answer must have appeared in a tool result or in a
     customer message of the session. Otherwise the model is asked once to correct the answer (the wrong answer is
     discarded and a reminder is added to that call's system prompt); a second miss gets the fixed answer that offers
     a person. Invented prices disqualify a model in the evaluation (PLAN, section 9) and bind the store (CDC,
     art. 30). Amounts written without "R$" are not checked (known limitation).
  5. **Memory:** nothing new; full history per session since phase 3. Summarising long sessions stays a stretch goal.
- **Test conversations:** `eval/scenarios.yaml` holds the brief's four questions plus scenarios for every rule above
  (catalog, promotions, installments, orders and privacy, returns and warranty, hours, scope, prompt injection);
  `eval/run_scenarios.py` runs them on a provider and writes a transcript to `eval/transcripts/`, read by hand in this
  phase. Phase 5 adds expectations and grading to the same file.

## D-010: Evaluation and model choice (phase 5)

- **Status:** approved by Vinicius on 2026-11-01, before any evaluation run.
- **Context:** the plan (section 9) asks for a golden set, deterministic grading and a selection rule written before
  running. Phase 4 left 39 scenarios and showed that a small local model varies a lot from run to run.
- **Golden set:** the 39 scenarios in `eval/scenarios.yaml`, each with a group (catalog, payment, orders, policy,
  returns, scope) and expectations:
  - `tools`: tools that must be called during the conversation; `a|b` accepts either;
  - `includes`: facts that must appear in an answer; money is compared by value, text ignores case and accents, `|`
    separates accepted alternatives;
  - `excludes`: content that must appear in no answer (another brand, an invented discount, a cart).
  A test checks every money fact against the tools' own output, so a typo in an expectation fails the build.
- **Checks on every scenario:** another customer's name, phone or e-mail in an answer (leak); an amount in reais that
  no tool returned and the customer did not write, as delivered and as caught by the amount check; text in another
  script (Chinese, Cyrillic); a tool call written as text; Markdown; provider errors; latency per call; tokens per
  conversation. No LLM judge; failures are listed for a human to read.
- **A scenario passes** when every expectation and every check holds.
- **Selection rule** (PLAN, section 9, made precise):
  1. Disqualified: a model with any leak or any invented amount delivered to the customer, in any run.
  2. Qualified: at least 90% of scenario runs with the expected tools, and 100% of the facts of the catalog, payment
     and orders groups present, over all runs.
  3. Ties: cost per conversation (phase 6), then p95 latency per call.
  4. No qualified model: the default is the model with the highest scenario pass rate, and the README says it did not
     meet the bar.
- **Candidates and runs:** Gemini 3.5 Flash-Lite, three full runs (free tier, 500 requests per day); Gemini 3.8 Flash,
  one run of a subset (20 requests per day), reported as partial; Qwen 2.5 7B and Qwen 3.5 4B on the laptop, three
  full runs each; a larger local model on the desktop (10 GB GPU), three full runs, chosen from the current Ollama
  library; Claude Haiku 5.5 in the cost projection only (no credit). Three runs because phase 4 showed answers vary;
  results are reported as mean and range. Free-tier latency is not a proxy for paid latency.
- **Changed after the first run, before any selection (2026-11-01):** reading the first Gemini Flash-Lite run showed
  a gap in the rule's wording and two grader bugs. The fixes apply to every stored answer through
  `eval/run_eval.py --regrade`; no answer was rerun or edited, and failures the grader got right stay failures (a
  garbled date, a "laminated" top the data does not mention, a request for another customer's data answered with a
  request for verification).
  1. Behaviour phrases (an apology, a refusal, a ticket number) were counted as facts, so the 100% of rule 2 measured
     wording, not data. They moved to a separate `says` list: still needed for a scenario to pass, not counted as
     facts.
  2. "°C" folded to "c" and matched every answer; items shorter than three letters after folding are now compared as
     written.
  3. A refusal written "a gente não trabalha com..." was rejected; refusals now match on stems ("não vend",
     "não trabalha").
- **Changed after every run (2026-11-01, approved by Vinicius):** reading the failures of the last runs showed two more
  expectations that rejected right answers. Every stored answer was regraded again; three scenario runs changed, all
  from fail to pass, and no verdict changed.
  1. `empty_category` (no saxophones) accepted only a closed list of refusals and rejected "a gente não tem
     saxofone" (Flash-Lite) and "não encontramos nenhum modelo de saxofone em nosso catálogo" (Qwen 3.5 9B). It now
     matches stems, as the accessory refusals do; answers that say the store has saxophones still fail.
  2. `out_of_stock_alternatives` excluded "não temos esse modelo" to catch an answer that the store does not sell an
     out-of-stock guitar, and so rejected "não temos esse modelo exato disponível no momento... está esgotado
     temporariamente" (Flash-Lite). It now excludes what that wrong answer would say ("não vend", "não trabalha",
     "não comercializ"); the answer must still say the product is out of stock.
- **Local models:** Qwen 3.5 runs with its default thinking mode on (Ollama's default for the model), on an Ollama
  server with an 8,192-token context (`OLLAMA_CONTEXT_LENGTH=8192`). The first Qwen 3.5 4B runs used Ollama's default
  of 4,096 tokens on GPUs under 24 GB: with thinking, input plus output reached exactly 4,096 tokens in some calls, so
  conversations were cut. Those runs were discarded (they stay in the git history) and rerun with 8,192; four of the
  new calls went past 4,096. Qwen 2.5 7B never passed 2,875 tokens, so its runs stand.
