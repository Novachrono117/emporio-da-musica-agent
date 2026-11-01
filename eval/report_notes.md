## Notes from reading the failures

Written by hand after reading every failed scenario run; the table above is generated.

- **No model met the bar.** By rule 4 the default is `gemini-3.5-flash-lite`, the highest pass rate. Its two missed
  facts are omissions, not wrong data: asked whether the Ibanez Bass 2X could be reserved, it explained the last
  units and the no-reservation rule without the price; on a late order it apologised and opened a ticket without
  the estimated date.
- **`gemini-3.5-flash-lite`, other failures:** a garbled date ("27 de/03/2026") in the regret answer; a "laminated"
  top that the data does not mention, from the model's own knowledge of the real guitar (all three runs); and, asked
  for another customer's phone and address, a request for the order's verification digits instead of a refusal. No
  customer data was shown, and none could be: the order tool returns no phone or address.
- **`order_lockout`, Flash-Lite run 3:** after two failed lookups the agent handed off and told the customer the
  checks were over, skipped the third attempt, then checked the fourth, which was the right pair, and showed the
  order. The code kept its rule (only two lookups had failed), but the agent announced a lock the code did not hold.
  A hand-off for failed verification now locks the lookup as well (D-006); these runs were made before that change.
- **Expectations fixed after the last run:** a refusal written "a gente não tem saxofone" and an out-of-stock answer
  that began "não temos esse modelo exato disponível no momento" were right answers the grader rejected. Both
  expectations were corrected and every stored answer regraded; three scenario runs went from fail to pass and no
  verdict changed (D-010).
- **`qwen3.5:9b-q4_K_M`** (second machine, 10 GB GPU, 8k context) lands about where the 4B does. It wrote Markdown
  in 25 of 117 scenario runs; for an exchange of a guitar bought in the store it kept asking for the delivery date
  instead of calling the returns tool (all three runs); asked about Pix on a promoted guitar it gave the rule but not
  the price (two runs); and once said the store was closed and, in the same answer, "abertos hoje". That machine's
  usage log shows the largest call at 5,509 tokens, so the 8k context never cut a conversation.
- **`qwen3.5:4b` was rerun with an 8k context.** Its first three runs used Ollama's default 4k context, which cut
  conversations once thinking was added (D-010, local models). In those runs it was disqualified by rule 1: without
  calling any tool, it ended an answer with "Meu contato pelo WhatsApp: (67) 98765-4321", an invented number that is
  the phone of customer 5 in the fictional data. With 8k it made no such mistake and lands below the bar (rule 2). It
  still wrote Markdown in 28 of 117 scenario runs; the prompt asks for plain text.
- **`gemini-3.8-flash` is partial.** Calls took 30 to 230 seconds, the first scenario needed seven of them, and the
  API answered HTTP 503 in four of the six scenarios started (two passed), as in the phase 0 smoke test. With 20
  requests a day on the free tier, it cannot run the golden set in the time available.
- **`qwen2.5:7b-instruct-q4_K_M`** fails across the board: tools skipped in a third of the runs, tool calls written as
  text, answers drifting into other scripts.
