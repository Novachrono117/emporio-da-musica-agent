# Example conversations

Five conversations with the default model, Gemini 3.5 Flash-Lite (`docs/EVAL.md`). Each comes from a single run of
`scripts/run_examples.py` on 2026-11-01 with the final code; the customer messages are in `conversations.yaml`
(`docs/DECISIONS.md`, D-011). Every tool call is folded under the step that made it, with the result the model read.
The files were not edited by hand; what went wrong is listed below.

| Conversation | What it shows |
|---|---|
| [Guitars under R$ 1,000, then installments and Pix](01-guitars-and-payment.md) | catalog search with a price limit; installments and Pix price computed in code |
| [A late order](02-late-order.md) | verification by order number and phone ending, a late delivery, a hand-off with a ticket |
| [Regret after an online purchase](03-regret-online.md) | the 7-day regret deadline computed in code, the request recorded for a person |
| [Strings, another customer's data and a prompt injection](04-scope-and-privacy.md) | out of scope, privacy, an instruction to ignore the rules |
| [A defect after 30 days](05-warranty-after-30-days.md) | the legal warranty is never denied; a person takes over |

## What went wrong

Read by hand after the run. Every amount, date, ticket and contact in the five conversations comes from a tool
result.

- **A late order:** the hand-off used the reason `order_verification_failed`, although the customer had just been
  verified; the answer to the customer was right. No lookup had failed, so the lookup was not locked (D-006). The
  first message also called the shipping policy tool, which was not needed before asking for the phone ending.
- **Regret after an online purchase:** the request was recorded one message before the customer asked for it, and
  the purchase date was taken to be the delivery date, which the customer did not say. The deadline does not change:
  it counts from delivery.

## Running them again

```bash
python scripts/run_examples.py --min-interval 4.5
```

The five conversations took 25 model calls. The answers change from run to run; the evaluation measures how often
they are wrong.
