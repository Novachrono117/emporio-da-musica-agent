"""Run the example conversations in examples/conversations.yaml and write one Markdown file each (DECISIONS.md, D-011).

Each conversation runs once, on the default model unless --provider says otherwise, with the evaluation's runner:
a fresh session, a fixed store time and a temporary ticket log. The file shows every customer message, every tool
call with its result and every answer, and is never edited by hand. A provider error writes nothing; run that
conversation again with --only.

Usage:
    python scripts/run_examples.py --min-interval 4.5
    python scripts/run_examples.py --only 02-late-order --min-interval 4.5
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from run_scenarios import DEFAULT_NOW, CountingUsage, Outcome, Throttled, run_scenario  # noqa: E402

from emporio.config import STORE_TZ, agent_now  # noqa: E402
from emporio.data.memory import InMemoryStore  # noqa: E402
from emporio.data.policy import load_policy_manual  # noqa: E402
from emporio.llm import DEFAULT_PROVIDER, PROVIDERS, create_client, redact  # noqa: E402
from emporio.llm.base import LLMError  # noqa: E402

EXAMPLES = ROOT / "examples"
CONVERSATIONS = EXAMPLES / "conversations.yaml"
WEEKDAYS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def render(example: dict[str, Any], outcome: Outcome, provider: str, model: str) -> str:
    store_time = agent_now(example.get("now", DEFAULT_NOW))
    usage = outcome.usage
    lines = [
        f"# {example['title']}",
        "",
        f"What it shows: {example['shows']}",
        "",
        f"Model `{provider} / {model}`, run on {datetime.now(STORE_TZ):%Y-%m-%d} with the store clock at "
        f"{store_time:%d/%m/%Y %H:%M} ({WEEKDAYS[store_time.weekday()]}). {usage.get('calls', 0)} model calls, "
        f"{usage.get('input_tokens', 0):,} input and {usage.get('output_tokens', 0):,} output tokens. Written by "
        "`scripts/run_examples.py` from a single run; not edited by hand.",
    ]
    results = {m["tool_call_id"]: m["content"] for m in outcome.messages if m["role"] == "tool"}
    for message in outcome.messages:
        if message["role"] == "user":
            lines += ["", f"**Cliente:** {message['content']}"]
        elif message["role"] == "assistant" and message.get("tool_calls"):
            for call in message["tool_calls"]:
                arguments = json.dumps(call["arguments"], ensure_ascii=False)
                lines += [
                    "",
                    "<details>",
                    f"<summary>tool: <code>{call['name']}({arguments})</code></summary>",
                    "",
                    "```json",
                    _pretty(results.get(call["id"], "")),
                    "```",
                    "",
                    "</details>",
                ]
        elif message["role"] == "assistant":
            lines += ["", f"**Assistente:** {message['content']}"]
    if outcome.corrections:
        lines += ["", f"The amount check (D-009) asked the model to correct {outcome.corrections} answer(s)."]
    return "\n".join(lines) + "\n"


def _pretty(content: str) -> str:
    try:
        return json.dumps(json.loads(content), ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=PROVIDERS, default=DEFAULT_PROVIDER)
    parser.add_argument("--model")
    parser.add_argument("--only", help="comma-separated file names, e.g. 02-late-order")
    parser.add_argument("--min-interval", type=float, default=0.0, help="seconds between model calls")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")

    examples = yaml.safe_load(CONVERSATIONS.read_text(encoding="utf-8"))
    if args.only:
        wanted = set(args.only.split(","))
        examples = [e for e in examples if e["file"] in wanted]
    try:
        llm = Throttled(create_client(args.provider, args.model), args.min_interval)
    except LLMError as error:
        print(redact(str(error)))
        return 2

    store, manual, usage = InMemoryStore.from_csv(), load_policy_manual(), CountingUsage()
    failed = 0
    with tempfile.TemporaryDirectory() as tickets_dir:
        for example in examples:
            scenario = {**example, "id": example["file"]}
            outcome = run_scenario(llm, scenario, store, manual, Path(tickets_dir), usage)
            if outcome.error:
                failed += 1
                print(f"ERROR {example['file']}: {outcome.error}")
                continue
            path = EXAMPLES / f"{example['file']}.md"
            path.write_text(render(example, outcome, llm.provider, llm.model), encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path} ({outcome.seconds:.1f} s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
