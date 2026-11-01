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

Findings from reading the whole manual and a quick integrity check of the orders, before phase 1. The proposals were
approved on 2026-11-01, several of them revised after a check against consumer law: the rules in force are in
`docs/DECISIONS.md`, D-005, which wins wherever it differs from a "Proposed" line below.

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

`src/emporio/data/loader.py` applies every rule below, and `tests/test_loader.py` covers them.

**What the files contain**

- No empty value in a required column, no value with stray spaces, and unique IDs in every table. Product IDs run from
  81 to 145; prices from R$ 159,90 to R$ 19.567,00, never with more than two decimals.
- Referential integrity holds: every product has a known category, every order a known customer and at least one item,
  every item a known order and product, every promotion a known product.
- Categories 6, 7 and 8 (wind instruments and orchestral strings) have no products.
- `specs` is valid JSON in all 65 products. Its keys depend on the instrument: `color` is everywhere; most string
  instruments have `top`, `back_sides`, `neck`, `scale`, `strings` and `electronics`; drum kits have `shells`, `pieces`
  and `hardware`.
- Products: 62 `active`, 2 `discontinued`, 1 `coming_soon`. Product 96 is active with no stock, 113 is discontinued
  with no stock, 136 is discontinued with 13 units, and 130 is coming soon with 2 units.
- Product 130 is coming soon, yet it appears in delivered order 3 and pending order 14. Orders are shown as recorded
  (D-005, rule 8) and the product is not quoted while it is coming soon (rule 10). Found in phase 2.
- Products 135 to 144 have generic names (for example "Music Man Bass 1X Electric Bass"). In seven of them the
  description names another brand or model, and some contradict the specs too (found in phase 2):

  | Product | Name says | Description says |
  |---|---|---|
  | 135 | Music Man bass | Fender Jazz Bass, alder body (specs: ash) |
  | 136 | Ibanez bass | Precision bass |
  | 137 | Yamaha bass | Ibanez, 5 strings (specs: 4) |
  | 139 | Yamaha drum kit | Pearl Export, poplar and mahogany shells (specs: maple) |
  | 140 | Pearl drum kit | Tama, birch shells (specs: maple) |
  | 142 | Korg synthesizer | Roland workstation, 88 keys (specs: 61) |
  | 144 | Roland synthesizer | Yamaha arranger keyboard |

  Products 138, 141 and 143 agree with their names.
- Customers: names are unique; every phone follows `(NN) NNNNN-NNNN`; **two customers share one e-mail address**, so a
  customer is never identified by e-mail.
- Orders: 4 `pending`, 4 `confirmed`, 1 `shipped`, 7 `delivered`, 4 `cancelled`. Only shipped and delivered orders
  carry a tracking code and an estimated delivery date, and the 8 codes follow the manual's format (5.3: `BR`, 9
  alphanumerics, `BR`). Only the cancelled orders have notes. Payment methods: `pix`, `debit`, `boleto`, `credit_3x`,
  `credit_6x`, `credit_12x`.
- Promotions: 25 rows, 4 active (products 127, 121, 90 and 94), never more than one active per product. Products 93, 96
  and 99 have several promotions, none active.

**Cleaning and parsing**

- Files are read as UTF-8, tolerating a BOM, and every value is stripped.
- Money becomes a `Decimal` with two places; IDs, stock and quantities become integers; dates become ISO dates.
- Empty `tracking_code`, `estimated_delivery` and `notes` become `None`.
- `payment_method` is split into a method and a number of installments (`credit_6x` gives credit and 6; the other
  methods give 1).
- `specs` is parsed into a read-only mapping.
- Availability is derived from status and stock (D-005, rule 10).
- Nothing is corrected: totals that differ from their items stay as recorded (D-005, rule 8).

**Validation:** the loader raises `DataError` instead of loading half-clean data when it finds a duplicate ID, an
unknown reference, an order without items, more than one active promotion for a product, an unknown status or payment
method, invalid JSON, an amount that is not positive or has more than two decimals, or an empty required text. Error
messages name the row by its ID only, never by customer data.

**Policy manual** (`src/emporio/data/policy.py`, covered by `tests/test_policy.py`)

- pypdf's layout mode keeps each heading at the start of its own line, so the manual is read line by line instead of
  splitting a single stream of words. The repeated page header and the "Página N" footers are dropped, which joins
  sections 5.2, 7.2 and 9 across their page breaks.
- The result has 29 sections: the cover (`0`) and chapters 1 to 10 with their sub-sections. A heading counts only when
  it follows the previous number, so numbers inside the text (for example "13.709/2018") never open a section.
- Table columns are joined with ` | ` and bullets are normalised.
- Contradictions stay exactly as written; D-005 decides how the agent handles them.

**The agent's "today"** (`src/emporio/config.py`): D-005, rule 7.
