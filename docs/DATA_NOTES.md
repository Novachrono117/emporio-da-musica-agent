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

## Profiling and cleaning (phase 1)

To be filled in phase 1: types, nulls, duplicates, ID ranges, referential integrity, `specs` JSON, availability rules,
promotions, order status values, tracking codes, "today", and the contradictions inside the policy manual.
