# Data notes

How the store data was received, what was found in it and how each issue is handled. Raw files in `data/` are never
edited; every fix happens in code and is recorded here.

## Provenance

The files come from the case zip (`Desafio_Técnico_AI_Engineer_2026-20260616T150750Z-3-001.zip`, folder `data/`) and
were extracted without changes. The case statement PDF from the same zip is not part of the repository.

| File | Bytes | SHA-256 |
|---|---:|---|
| `desafio_tecnico_ai_eng - categories.csv` | 756 | `7a7901e16c8c6357a956031ada45a6fd6a4cc9bd7bc1edc05448cc55b01b0a9e` |
| `desafio_tecnico_ai_eng - customers.csv` | 3756 | `1cd724dc86eac6258913cc890abf23d3893c57a99c9325ebfb91dfad3c7b0f37` |
| `desafio_tecnico_ai_eng - order_items.csv` | 230 | `7656eb681821d48e0c932f61d3188309b955c25446578235f2d8e69604b0f0bc` |
| `desafio_tecnico_ai_eng - orders.csv` | 1324 | `deb9c2480605d8d22117d569f0045fd156c5e9a58ffeebb847ff61b3b9512fd5` |
| `desafio_tecnico_ai_eng - products.csv` | 22399 | `78d911d96ee891abb163b6c858e895025aa530ab27d0290540f05d5098377c12` |
| `desafio_tecnico_ai_eng - promotions.csv` | 839 | `cbe08c7e91b00437c0c00a7ef1486deba73de52d23e3f97f51a7dbd557d759e0` |
| `políticas_da_loja.pdf` | 180519 | `b7527f96896929f4ba929de117651c6717e25b7a3b92b34bc54d5ba32f6156f7` |

`.gitattributes` marks `data/**` as `-text`, so Git stores these bytes as they are (see `DECISIONS.md`, D-002).

## First observations (phase 0)

- All six CSVs decode as UTF-8 **without** a BOM (the plan assumed a BOM; the loader should still tolerate one).
- Line endings are CRLF and the last row has no trailing newline.
- Row counts (header excluded): categories 9, customers 50, order_items 22, orders 20, products 65, promotions 25. They
  match the plan.

## First read of the manual and the orders (phase 0)

Findings from reading the whole manual and a quick integrity check of the orders, before phase 1. Each "Proposed" line is
a proposal until Vinicius approves it in phase 1.

**Policy manual (`políticas_da_loja.pdf`, 8 pages, version 2.1, June 2025)**

- **Text extraction:** `pypdf`'s default `extract_text()` returns one word per line (`"word \n"`). Every page repeats the
  header "Empório da Música Manual de Políticas e Procedimentos" and ends with "Página N"; sections 5.2, 7.2 and 9 cross
  a page break. Proposed: normalise whitespace, drop header and footer, then split on the numbered headings (1. to 10.,
  with sub-sections such as 3.1).
- **Installments, a contradiction inside section 3:** the payment table says credit card "até 12x sem juros, parcela
  mínima de R$ 100,00"; section 3.1 sets tiers: up to 3x with no minimum "exceto abaixo de R$ 50,00", 4x to 6x with a
  R$ 80 minimum, 7x to 12x with a R$ 100 minimum. Proposed: 3.1 wins (it is the specific rule), and "exceto abaixo de
  R$ 50,00" reads as "no installment below R$ 50".
- **Contact data, two contradictions:** e-mail `contato@emporiodamusica.com.br` on the cover and
  `contato@empóriodamusica.com.br` in the company table (1.2); phone/WhatsApp (67) 3341-4444 on the cover and in 1.2, but
  section 7 names (67) 3321-4500 as the WhatsApp channel. The plan's example rule "the company table wins" would pick the
  accented e-mail, which looks like the typo. Proposed: unaccented e-mail; (67) 3341-4444 as the phone (it appears twice,
  in both "company data" places) and record the WhatsApp conflict in the README.
- **Warranty, two rules that must be told together:** 4.2 allows a defect exchange at the store up to 30 days after the
  purchase, then sends the customer to the manufacturer; 8.1 states the legal warranty of 90 days from receipt (CDC).
  Proposed: the agent cites both and hands off to a human for defects between day 31 and day 90 (section 10: "consult
  management" when in doubt).
- **Regret right (4.1) covers online purchases only,** and `orders.csv` has no sales channel column. Proposed: the agent
  asks how the purchase was made before applying 4.1.
- **Accessories:** 7.1 says to suggest partner stores "when possible", but no partner list exists. Proposed: redirect
  politely without naming any store.
- **Seasonal campaigns (6.1)** such as Black Friday (November) are descriptions, not offers. Only rows with
  `is_active = 1` in `promotions.csv` apply (7.3: never promise an expired discount).
- **Hours (2):** closed on Sundays and holidays; outside hours the assistant must say when people are back (7.1). This
  needs the current time as well as the date.

**Orders (quick check, all 20 orders)**

- **Dates run from 2025-10-15 to 2026-03-22,** not only 2025 as the plan says. With the real date (Oct 31st 2026) as
  "today", the four `pending` orders would be seven months old and the `shipped` order 8 (estimated delivery 2026-02-28)
  eight months late. Proposed: default `EMPORIO_TODAY` to a snapshot date right after the last order (for example
  2026-03-23) and state it in the README.
- **Two totals differ from the sum of the items at list price:** order 3 (R$ 3.450 vs 2 x R$ 1.749 = R$ 3.498) and order
  20 (R$ 1.400 vs R$ 1.488). No discount is recorded. Proposed: the agent reports the recorded total and never recomputes
  a past order.
- **Three orders break the 3.1 installment minimums:** 9 (6x R$ 58,32), 16 (6x R$ 71,65) and 18 (12x R$ 38,32). Proposed:
  historical orders are shown as recorded; the rules apply to new quotes only.
- `products.status` has three values: `active` (62), `discontinued` (2) and `coming_soon` (1); two products have stock 0.
  Four promotions are active (products 127, 121, 90 and 94), at most one per product.

## Profiling and cleaning (phase 1)

To be filled in phase 1: types, nulls, duplicates, ID ranges, referential integrity, `specs` JSON, availability rules,
promotions, order status values, tracking codes, "today", and the contradictions inside the policy manual.
