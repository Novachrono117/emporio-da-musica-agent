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
