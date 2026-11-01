# Empório da Música agent: rules for Claude Code sessions

Technical case for the Artefact AI Engineer selection process. The plan is `docs/PLAN.md`; read it before any change.
Deadline: Tuesday, Nov 3rd 2026, 11:59 pm (BRT). After delivery, nothing in this repository changes.

## How we work

- **Vinicius decides the architecture.** Propose, explain the trade-off, and wait for his approval before changing an
  approved decision. Approved decisions go to `docs/DECISIONS.md` (context, options, choice, why).
- Work **one phase at a time** (`docs/PLAN.md`, section 11). A phase ends with its tests passing and a short entry in
  `docs/AI_WORKFLOW.md`: what was asked, what Claude produced, what he reviewed or changed.
- **Simplest solution that meets the brief.** No dependency without a reason written down.
- If the brief is ambiguous, pick a reasonable interpretation, record it in `docs/DECISIONS.md`, and continue.

## Code

- Python 3.12 or 3.13; code, docs, comments and commit messages in English. The agent replies to customers in Brazilian
  Portuguese.
- Raw files in `data/` are never edited; cleaning happens in code and is documented in `docs/DATA_NOTES.md`.
- Tools return structured data, validate inputs against strict schemas, and keep all arithmetic (prices, discounts,
  installments) in code, never in the model.
- Never expose another customer's data; order lookups require verification.
- LLM SDKs: check the current documentation before writing calls. For Claude, use the official `anthropic` SDK and do not
  send `temperature`, `top_p` or `top_k` (rejected by the API since Oct 21st 2026). For Gemini and Ollama, use the
  `openai` SDK against their OpenAI-compatible endpoints.
- Run `pytest` before every commit.

## Git and secrets

- Small commits, one concern each, descriptive messages. Commits written with Claude Code end with
  `Co-Authored-By: Claude <noreply@anthropic.com>`.
- Never force-push, never squash history: the brief asks for real commit history.
- API keys live only in `.env` (gitignored). Never print a key, never put one in a commit, a log or the chat.
  `.env.example` lists the variables with empty values.
- The case PDF and the zip received by e-mail stay out of git (see `.gitignore`).
