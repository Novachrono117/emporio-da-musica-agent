# Empório da Música: customer service agent

A text agent that answers the customers of Empório da Música, a fictional musical instrument store in Campo Grande/MS.
It looks up products, prices, promotions and orders in the store's data, applies the store's policies (payment,
returns, warranty, shipping, hours, privacy), computes every price, installment and deadline in code, and hands the
conversation to a person when a human must decide. Customers write in Portuguese and the agent answers in Portuguese;
the code and the documents are in English.

It runs as a command-line chat on three providers: Gemini (the default, chosen by the evaluation), a local model through
Ollama, and Claude.

```text
Cliente: Gostei do Yamaha C40. Quanto fica em 6x no cartão?
Assistente: O Yamaha C40 sai por R$ 599,90 no cartão em até 6x sem juros, ficando 5x de R$ 99,98 e a última de
R$ 100,00. Ah, e o frete para Campo Grande é grátis! Se preferir pagar no Pix, tem desconto e sai por R$ 569,91.
```

The model only chose the tool and wrote the sentence: the installments, the last one absorbing the cents, the free
shipping and the Pix price came from `quote_payment` ([full conversation](examples/01-guitars-and-payment.md)).

## Contents

1. [Quick start](#quick-start)
2. [Architecture](#architecture)
3. [Technical decisions](#technical-decisions)
4. [Assumptions](#assumptions)
5. [Evaluation and model choice](#evaluation-and-model-choice)
6. [Cost projection](#cost-projection)
7. [Known limitations and what I would do with more time](#known-limitations-and-what-i-would-do-with-more-time)
8. [How I used coding assistants](#how-i-used-coding-assistants)
9. [Example conversations](#example-conversations)
10. [Repository map](#repository-map)

## Quick start

Requirements: Python 3.12 or 3.13, and one of: a Gemini API key (free from Google AI Studio), Ollama, or an Anthropic
API key.

```bash
git clone https://github.com/Novachrono117/emporio-da-musica-agent.git
cd emporio-da-musica-agent
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env               # Windows PowerShell: Copy-Item .env.example .env
pytest                             # 245 tests, no network
```

Then fill in `.env` for the provider you will use. Never commit it: it is in `.gitignore`.

### Gemini (default)

Create a key at [Google AI Studio](https://aistudio.google.com/apikey) and set `GEMINI_API_KEY` in `.env`. Then:

```bash
python -m emporio
```

This uses `gemini-3.5-flash-lite` through Gemini's OpenAI-compatible endpoint. The free tier allows 15 requests a
minute and 500 a day for this model; a conversation takes about three requests. Google may use free-tier prompts to
improve its products, which is acceptable for this fictional data only: real customer data needs the paid tier
(see [Assumptions](#assumptions)).

### Ollama (local)

Install [Ollama](https://ollama.com), pull the default local model and start the server with an 8k context:

```bash
ollama pull qwen3.5:4b
OLLAMA_CONTEXT_LENGTH=8192 ollama serve
python -m emporio --provider ollama
```

On Windows, set the variable for your user and restart the Ollama app (quit it from the tray, then open it again):

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "8192", "User")
```

The 8k context matters. Ollama defaults to 4,096 tokens on GPUs under 24 GB, its OpenAI-compatible API cannot change
that, and Qwen 3.5 thinks before answering: with 4k the conversations were cut and the model invented a phone number.
After the first answer, `curl http://localhost:11434/api/ps` should show `"context_length":8192`. Qwen 3.5 4B is a
3.4 GB download and runs on an 8 GB GPU. `OLLAMA_BASE_URL` in `.env` changes the endpoint (default
`http://localhost:11434/v1`).

### Claude

Set `ANTHROPIC_API_KEY` in `.env` and run `python -m emporio --provider anthropic` (Claude Haiku 5.5). The adapter
follows the current Anthropic SDK and is tested against recorded SDK objects, but it was never run against the live
API: there was no API credit during the project.

### Options

```bash
python -m emporio --verbose               # show each tool call and its result
python -m emporio --session <id>          # resume a saved conversation (the id is printed on exit)
python -m emporio --model <model>         # another model of the same provider
```

`LLM_PROVIDER` and `LLM_MODEL` in `.env` set the defaults. `EMPORIO_TODAY` sets the store's "today" (default
`2026-03-23`, the day after the last order in the data); `2026-03-29T10:00` also fixes the time, for example a Sunday
when the store is closed. Type `sair` to leave.

### Evaluation, examples and costs

```bash
python eval/run_eval.py --report                          # rebuild docs/EVAL.md from the stored results
python eval/run_eval.py --provider gemini --model gemini-3.5-flash-lite --reps 3 --min-interval 4.5
python eval/run_eval.py --provider ollama --model qwen3.5:4b --reps 3
python scripts/run_examples.py --min-interval 4.5         # regenerate the example conversations
python scripts/cost_report.py                             # rebuild docs/COSTS.md
```

A full evaluation run on Gemini takes about 115 requests; `--min-interval 4.5` keeps it under the free tier's rate
limit, and an interrupted run resumes where it stopped.

## Architecture

```text
customer (CLI: python -m emporio)
   |
Agent loop (agent/loop.py): up to 6 tool rounds per message, amount check, session saved as JSON
   |-- system prompt in Portuguese (agent/prompts.py)
   |-- LLM interface (llm/base.py)
   |     |-- AnthropicClient: Claude, official anthropic SDK
   |     |-- OpenAICompatClient: Gemini and Ollama, openai SDK on their OpenAI-compatible endpoints
   |
Tools (tools/): JSON schemas, inputs validated in code, structured results
   |-- search_products, get_product_details --+
   |-- get_order_status (verification)        +--> StoreRepository (in memory) <-- cleaned CSVs (data/loader.py)
   |-- quote_payment (Pix, installments)    --+
   |-- check_return_options (deadlines)
   |-- get_store_policy (by topic) ---------------> the manual, parsed from the PDF into 29 sections
   |-- register_complaint, handoff_to_human ------> ticket log (tickets/, kept out of git)
```

Each customer message goes to the model with the history and the eight tool definitions. When the model asks for tools,
the loop validates the arguments, runs the tools and sends the results back, until the model answers in text. The
answer is checked before it reaches the customer, and the session is saved.

| Tool | What it does |
|---|---|
| `search_products` | Search by name, category and price limit; availability from stock and status |
| `get_product_details` | One product: price, promotion, availability, specs |
| `quote_payment` | Cart total, installments, Pix price and shipping, all computed in code |
| `get_order_status` | An order, only after the order number and the last 4 phone digits match |
| `check_return_options` | Regret, exchange and warranty deadlines for the customer's dates |
| `get_store_policy` | The manual sections of a topic, plus notes where the rules resolve a conflict |
| `register_complaint` | Records a complaint for the person in charge (24 business hours) |
| `handoff_to_human` | Records a ticket and returns the contacts and whether the store is open |

## Technical decisions

Each decision has its context, options and reason in [docs/DECISIONS.md](docs/DECISIONS.md) (D-001 to D-011). The
short version:

**Approach: function calling with typed tools, no framework.** Price, stock and order questions have exact answers in
structured data, so the model gets tools instead of free-form SQL or a retrieval index. Tools keep filtering and
arithmetic in code (`Decimal` from the CSV to the answer), never expose another customer's data, and are unit-tested
without a model. The loop is about 130 lines of my own code instead of LangChain or a similar framework: it is easy to
read, works the same on three providers, and runs in tests with a scripted fake model. A SQL agent would be more
flexible but harder to make safe and to test (D-004, D-006, D-008).

**Retrieval of policies: by topic, no vector database.** The manual is 8 pages (about 3,000 tokens). The loader splits
it into its 29 numbered sections, and `get_store_policy(topic)` returns the sections of one topic (hours, payment,
returns, shipping, promotions, warranty, privacy, contact) with notes where the manual contradicts itself or the law.
Embeddings would add a dependency and failure modes without better recall at this size. With hundreds of documents or a
policy base that changes every week, I would add hybrid search (keywords plus embeddings) behind the same tool.

**Model and provider: chosen by an evaluation, not by brand.** One interface, two adapters: the official `anthropic` SDK
for Claude and the `openai` SDK for Gemini and Ollama. Five models ran a golden set of 39 conversations, graded in code
with a selection rule written before the first run. No model met the bar, and by the fallback rule the default is
Gemini 3.5 Flash-Lite, the best of them (93% of conversations). The local default is Qwen 3.5 4B, the best model that
fits an 8 GB GPU. See [Evaluation](#evaluation-and-model-choice) (D-003, D-010).

**Prompt strategy: short, tool-first, rules next to the data.** The system prompt is in Portuguese, the customers'
language, and fits in one screen: the persona, a table that routes each kind of question to its tool, and a short list
of things the agent never does. The first prompt spelled out every rule, and the local model stopped calling tools; a
side-by-side run showed the length was the cause. Situational rules now travel inside the tool results ("the delivery
date has passed: apologise and offer a person"), where the model reads them at the moment they apply. The prompt carries
the store date and whether the store is open, never the clock time, so it stays identical between calls and can be
cached (D-009).

**Guardrails in code, not only in the prompt:**

- Prices, installments, discounts and deadlines are computed by tools; the model only quotes them.
- Every amount in reais in an answer must have come from a tool result or from the customer. Otherwise the answer is
  discarded and the model asked once to correct it; a second miss gets a fixed answer that offers a person (D-009).
- `quote_payment` accepts only product ids a search returned in the session: a local model once quoted invented ids.
- Orders need the order number and the last 4 digits of the phone, checked in code; the model never sees a phone
  number. Three failed lookups, or a hand-off for failed verification, lock order lookups for the session (D-006).
- A conversation that needs more than 6 tool rounds for one message gets the fixed answer instead of looping.

**Interface: a CLI.** The brief puts the agent first. A command-line chat is enough to use and test it, and the same
loop runs the evaluation and the examples. A web UI is the first thing I would add.

**Conversation history: kept and resumable.** Each session is a JSON file in `sessions/` (out of git: it holds customer
data) with the full history, so the agent remembers an order verified two messages earlier and a conversation can be
resumed with `--session`. The session also keeps the failed order lookups and the products shown, so the guardrails
survive a restart. Summarising long sessions was not needed at this size.

**Data treatment.** The CSVs stay byte for byte as received (D-002); the loader validates and cleans them in code, and
[docs/DATA_NOTES.md](docs/DATA_NOTES.md) lists every issue found and how it was handled. Seven products had
descriptions of another brand or model (a "Korg" described as an 88-key Roland); the loader drops those descriptions,
because the agent would repeat whichever text it read (D-007). The manual is read with `pypdf`, page headers and footers
removed.

**Business rules.** The manual contradicts itself in places, and a few rules sit in tension with Brazilian consumer
law. [D-005](docs/DECISIONS.md#d-005-business-rules-from-the-data-the-manual-and-the-law) resolves each case, with the
law cited; the main ones are under [Assumptions](#assumptions).

## Assumptions

The brief asks to document reasonable interpretations. The main ones:

- **Today is 2026-03-23** (the day after the last order), in store time UTC-4 (Campo Grande has no daylight saving
  time, while Brasília is UTC-3). The time of day comes from the real clock.
- **Customers write in Portuguese** and get answers in Portuguese.
- **Contacts:** the manual gives two e-mails (with and without an accent) and two numbers for WhatsApp. The agent uses
  `contato@emporiodamusica.com.br`, phone (67) 3341-4444 and WhatsApp (67) 3321-4500 (section 7, the one about the
  channel).
- **Installments:** section 3.1 wins over the summary table in section 3: at least R$ 50 per installment up to 3x,
  R$ 80 up to 6x, R$ 100 up to 12x, no interest. The 5% Pix discount never applies on top of a promotion (6.2).
- **Regret** (7 days from delivery) applies only to purchases made outside the store (CDC, art. 49); in-store purchases
  have the 7-day preference exchange instead. The manual refunds within 10 business days while the law says
  "immediately"; the agent states the store's policy.
- **Defects after 30 days:** the manual sends the customer to the manufacturer (4.2), but store and manufacturer answer
  jointly (CDC, art. 18). The agent never denies the warranty and hands the case to a person.
- **Accessories** (strings, cables, cases) are not sold; the agent says so without naming another store.
- **Order lookup** needs the order number and the last 4 phone digits; customers are never identified by e-mail,
  because two of them share one.
- **Past orders** show their recorded total and installments, even where they break today's rules.

## Evaluation and model choice

Method ([D-010](docs/DECISIONS.md#d-010-evaluation-and-model-choice-phase-5)): 39 multi-turn conversations in
[eval/scenarios.yaml](eval/scenarios.yaml), covering the brief's four examples, the catalog, promotions, payment,
orders and privacy, returns and warranty, hours, out-of-scope requests and prompt injection. Each lists the tools that
must be called, the facts that must appear (money compared by value), the behaviour expected (an apology, a refusal, a
ticket) and content that must never appear. Every answer is also checked for another customer's data, amounts no tool
returned, other scripts, tool calls written as text and Markdown. No LLM judge: grading is deterministic, and every
failure is listed for a person to read. A test checks every expected amount and date against the tools' own output.

The selection rule, written before the first run: disqualify any leak or invented amount; qualify with at least 90% of
conversations calling the expected tools and 100% of the catalog, payment and orders facts; break ties by cost, then
latency; if nothing qualifies, take the highest pass rate and say so.

| Model | Runs | Pass rate | Expected tools | Facts | Leaks | Latency p50 / p95 | Verdict |
|---|---:|---|---:|---:|---:|---|---|
| Gemini 3.5 Flash-Lite | 3 | 93% (90%, 92%, 97%) | 100% | 98% | 0 | 4.5 s / 4.9 s | default, below the bar |
| Qwen 3.5 9B (local, 10 GB GPU) | 3 | 64% | 90% | 92% | 0 | 2.3 s / 6.2 s | below the bar |
| Qwen 3.5 4B (local, 8 GB GPU) | 3 | 62% | 91% | 90% | 0 | 2.2 s / 4.9 s | below the bar, local default |
| Qwen 2.5 7B (local) | 3 | 44% | 63% | 57% | 0 | 0.8 s / 2.5 s | below the bar |
| Gemini 3.8 Flash | partial | 2 of 6 | | | 0 | 92 s / 234 s | not ranked (HTTP 503, 20 requests a day) |

No model met the bar. Flash-Lite missed two facts in 117 conversations, both omissions rather than wrong data (a price
not repeated, a delivery date not stated); its other failures are a garbled date, a "laminated" guitar top that came
from the model's own knowledge instead of the data, and one request for another customer's data answered with a
request for verification instead of a refusal. The local models write Markdown in about a quarter of the conversations
and skip tools more often. Full table and every failure: [docs/EVAL.md](docs/EVAL.md). Latency was measured on Gemini's
free tier and on local GPUs, so it says little about a paid tier.

Reading the failures also fixed things outside the models: two grader bugs and two expectations that rejected right
answers (all answers regraded, no verdict changed), a 4k context that had cut the first local runs, and an agent that
announced an order lock the code did not hold (now it does). D-010 lists every change.

## Cost projection

From the tokens measured in the evaluation (a conversation averages 2.9 model calls, about 7,000 input and 160 output
tokens) and the paid-tier prices read on 2026-11-01. Details, p90 and sources: [docs/COSTS.md](docs/COSTS.md).

| Model | Per conversation | Month, 30 a day | Month, 100 a day | Month, 300 a day |
|---|---:|---:|---:|---:|
| Gemini 3.5 Flash-Lite (measured) | US$ 0.0025 | US$ 2.23 | US$ 7.44 | US$ 22.32 |
| Claude Haiku 5.5 (projected) | US$ 0.0009 | US$ 0.77 | US$ 2.57 | US$ 7.71 |
| Claude Haiku 5.5 with prompt caching | US$ 0.0006 | US$ 0.49 | US$ 1.65 | US$ 4.94 |

At 100 conversations a day the default model costs about R$ 40 a month (1 USD = R$ 5,4212). A rented GPU machine for a
local model (Azure T4 in Brazil South) costs US$ 652.62 a month and only pays for itself above about 8,770 conversations
a day, with a model that did not meet the bar. Claude's numbers reuse Gemini's token counts, so they are a projection.

## Known limitations and what I would do with more time

Limitations:

- **The default model did not meet the bar.** It missed two facts and once answered a request for another customer's
  data with a request for verification (nothing was exposed: the order tool returns no personal data).
- **The amount check catches invented amounts, not real amounts attached to the wrong thing** (a real price quoted for
  another product), and amounts written without "R$".
- **Gemini fills gaps from its own knowledge** (it called a guitar top "laminated" in every run, which the data does not
  say), even though the prompt tells it to say when a tool did not return a detail.
- **The order lock is per session:** a new session starts the count again. A real deployment would count per order and
  per caller.
- **Local models need Ollama's 8k context** (see [Quick start](#ollama-local)).
- **Claude was never run live** (no API credit), and its costs are projected from Gemini's tokens.
- **Holidays are not computed** in opening hours or deadlines.
- **Latency was measured on the free tier** and on local GPUs.
- **Real customer data needs a paid tier** under a data processing agreement: the free tier may use prompts to improve
  Google's products (LGPD).

With more time:

1. Run the evaluation on Claude Haiku 5.5, which costs a third of Flash-Lite on paper and supports strict tool schemas.
2. Add the cases the default model failed to the prompt or the tool notes, rerun, and keep the golden set growing with
   real conversations.
3. A small web UI (FastAPI or Streamlit) on top of the same loop, and a hand-off that reaches a real inbox.
4. Holidays in opening hours and deadlines, and an order lock per order and caller.
5. A database behind `StoreRepository` when the data grows or changes during the day (the interface is the seam,
   D-004).
6. An LLM judge for tone, calibrated against hand grades, next to the deterministic checks.

## How I used coding assistants

I built this with **Claude Code** (Claude Opus 5.5, in the Claude desktop app). The brief values the workflow, so it is
recorded phase by phase in [docs/AI_WORKFLOW.md](docs/AI_WORKFLOW.md): what I asked, what Claude produced, and what I
reviewed or changed.

How the work was organised:

- **Plan first.** The work followed a written plan, [docs/PLAN.md](docs/PLAN.md): deliverables, architecture, eight
  phases, risks. Claude drafted it from the brief and I reviewed it before any code.
- **I decide, Claude proposes.** Every architecture choice went to [docs/DECISIONS.md](docs/DECISIONS.md) as context,
  options, choice and reason, and waited for my approval. Several changed on review: I asked for a design that can
  grow (the repository interface of D-004), pushed back on the first tool contracts (two changes in D-006), chose to
  drop the contradictory product descriptions rather than annotate them (D-007), and asked for more test
  conversations than the brief's four.
- **One phase at a time, tests first-class.** Each phase ended with its tests passing (245 now, none of them calling a
  model or the network) and an entry in the workflow log. Commits are small and carry a `Co-Authored-By: Claude`
  trailer.
- **Current documentation over memory.** Before writing SDK calls, Claude read the current Anthropic and Google docs;
  that is how the project knew, for example, that Claude Haiku 5.5 rejects `temperature` and that Gemini's
  OpenAI-compatible endpoint keeps thought signatures in `extra_content`.
- **Two machines.** A laptop for development and a desktop with a larger GPU for the 9B local model and the clean-clone
  check, each with its own `.env`; API keys never went through the chat or the repository.

What the process caught, because results were read instead of trusted:

- The long first prompt made the local model stop calling tools; a side-by-side run found the cause.
- The grader counted wording as facts and had two bugs; fixed and recorded, every answer regraded.
- Ollama's default 4k context was cutting conversations; found in the token counts, rerun at 8k.
- Gemini's OpenAI-compatible endpoint leaves thinking tokens out of `completion_tokens`; found while pricing, fixed in
  the adapter.
- An agent announcing an order lock the code did not hold; the code now holds it.

## Example conversations

Five conversations from single runs of the default model, never edited by hand, with every tool call and its result
([index and notes](examples/README.md)):

1. [Guitars under R$ 1,000, then installments and Pix](examples/01-guitars-and-payment.md)
2. [A late order, verified, then handed to a person](examples/02-late-order.md)
3. [Regret after an online purchase](examples/03-regret-online.md)
4. [Strings, another customer's data and a prompt injection](examples/04-scope-and-privacy.md)
5. [A defect after 30 days](examples/05-warranty-after-30-days.md)

## Repository map

```text
data/              the store's files, byte for byte as received
docs/              PLAN, DECISIONS (D-001 to D-011), DATA_NOTES, AI_WORKFLOW, EVAL, COSTS
src/emporio/       data/ (loader, models, repository), tools/, llm/ (adapters), agent/ (loop, prompt, guards,
                   sessions, usage log), company.py, tickets.py, cli.py
eval/              scenarios.yaml (golden set), run_eval.py, grading.py, results/, transcripts/ (phase 4)
examples/          the five conversations and their index
scripts/           run_examples.py, cost_report.py and pricing.yaml, smoke_test.py (phase 0)
tests/             245 tests, no network
```
