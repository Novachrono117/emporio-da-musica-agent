"""Run the test conversations in eval/scenarios.yaml on one provider and write a transcript to read by hand.

Phase 4 reads the transcripts; phase 5 adds expectations and grading to the same scenarios (DECISIONS.md, D-009).
Each scenario gets a fresh session, a fixed store time and its own ticket log in a temporary folder. Model calls go to
the usage log like any conversation.

Usage:
    python eval/run_scenarios.py --provider ollama
    python eval/run_scenarios.py --provider gemini --min-interval 4.5 --only brief_takamine_price,complaint
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from emporio.agent.loop import Agent
from emporio.agent.memory import new_session
from emporio.agent.usage import UsageLog
from emporio.config import STORE_TZ, agent_now
from emporio.data.memory import InMemoryStore
from emporio.data.policy import PolicyManual, load_policy_manual
from emporio.data.repository import StoreRepository
from emporio.llm import PROVIDERS, create_client, redact
from emporio.llm.base import LLMClient, LLMError, LLMResponse
from emporio.tickets import TicketLog
from emporio.tools.base import ToolContext

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "eval" / "scenarios.yaml"
TRANSCRIPTS = ROOT / "eval" / "transcripts"
DEFAULT_NOW = "2026-03-23T10:00"  # Monday, store open


class Throttled:
    """Keeps a minimum interval between model calls (Gemini free tier: 15 requests per minute on Flash-Lite)."""

    def __init__(self, llm: LLMClient, min_interval: float) -> None:
        self.llm = llm
        self.provider = llm.provider
        self.model = llm.model
        self.min_interval = min_interval
        self.calls = 0
        self._last = 0.0

    def complete(self, *args: Any) -> LLMResponse:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.calls += 1
        return self.llm.complete(*args)


class CountingUsage(UsageLog):
    def __init__(self, path: Path | None = None) -> None:
        super().__init__(path) if path else super().__init__()
        self.events: list[tuple[str, str]] = []

    def event(self, session_id: str, name: str, **details: Any) -> None:
        super().event(session_id, name, **details)
        self.events.append((session_id, name))


@dataclass
class Turn:
    customer: str
    tools: list[str]
    answer: str


@dataclass
class Outcome:
    scenario: dict[str, Any]
    turns: list[Turn] = field(default_factory=list)
    error: str = ""
    corrections: int = 0
    seconds: float = 0.0


def run_scenario(
    llm: LLMClient,
    scenario: dict[str, Any],
    store: StoreRepository,
    manual: PolicyManual,
    tickets_dir: Path,
    usage: CountingUsage,
) -> Outcome:
    now = agent_now(scenario.get("now", DEFAULT_NOW))
    ctx = ToolContext(store, manual, TicketLog(tickets_dir / f"{scenario['id']}.jsonl"), now=lambda: now)
    session = new_session(llm.provider, llm.model, datetime.now(STORE_TZ))
    calls: list[str] = []

    def on_tool(call, result):
        error = f" -> error {result['error']['code']}" if "error" in result else ""
        calls.append(f"{call.name}({json.dumps(call.arguments, ensure_ascii=False)}){error}")

    agent = Agent(llm, ctx, session, usage, on_tool=on_tool)
    outcome = Outcome(scenario)
    started = time.perf_counter()
    for text in scenario["turns"]:
        calls.clear()
        try:
            answer = agent.reply(text)
        except LLMError as error:
            outcome.error = redact(str(error))
            break
        outcome.turns.append(Turn(text, list(calls), answer))
    outcome.seconds = time.perf_counter() - started
    outcome.corrections = sum(1 for session_id, _ in usage.events if session_id == session.id)
    return outcome


def transcript(outcomes: list[Outcome], provider: str, model: str, calls: int) -> str:
    errors = sum(1 for o in outcomes if o.error)
    corrections = sum(o.corrections for o in outcomes)
    lines = [
        f"# Scenario transcripts: {provider} / {model}",
        "",
        f"Run on {datetime.now(STORE_TZ):%Y-%m-%d %H:%M} (store time UTC-4). Store date and time per scenario: "
        f"{DEFAULT_NOW} unless the scenario says otherwise. {len(outcomes)} scenarios, {calls} model calls, "
        f"{errors} provider errors, {corrections} amount corrections (D-009). Read by hand; not graded.",
    ]
    for outcome in outcomes:
        scenario = outcome.scenario
        lines += ["", f"## {scenario['id']}", "", f"*{scenario['purpose']}*"]
        if "now" in scenario:
            lines.append(f"Store time: {scenario['now']}.")
        for turn in outcome.turns:
            lines += ["", f"**Cliente:** {turn.customer}", ""]
            lines += [f"- tool: `{call}`" for call in turn.tools]
            if turn.tools:
                lines.append("")
            lines.append(f"**Assistente:** {turn.answer}")
        if outcome.corrections:
            lines += ["", f"Amount check fired {outcome.corrections} time(s)."]
        if outcome.error:
            lines += ["", f"Provider error: {outcome.error}"]
        lines += ["", f"({outcome.seconds:.1f} s)"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=PROVIDERS, required=True)
    parser.add_argument("--model")
    parser.add_argument("--only", help="comma-separated scenario ids")
    parser.add_argument("--min-interval", type=float, default=0.0, help="seconds between model calls")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")

    scenarios = yaml.safe_load(SCENARIOS.read_text(encoding="utf-8"))
    if args.only:
        wanted = set(args.only.split(","))
        scenarios = [s for s in scenarios if s["id"] in wanted]
    try:
        llm = Throttled(create_client(args.provider, args.model), args.min_interval)
    except LLMError as error:
        print(redact(str(error)))
        return 2

    store, manual, usage = InMemoryStore.from_csv(), load_policy_manual(), CountingUsage()
    outcomes = []
    with tempfile.TemporaryDirectory() as tickets_dir:
        for scenario in scenarios:
            outcome = run_scenario(llm, scenario, store, manual, Path(tickets_dir), usage)
            status = "ERROR" if outcome.error else "ok"
            print(f"{status:5} {scenario['id']} ({outcome.seconds:.1f} s, {outcome.corrections} corrections)")
            outcomes.append(outcome)

    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9.]+", "-", f"{llm.provider}-{llm.model}")
    path = TRANSCRIPTS / f"{slug}.md"
    path.write_text(transcript(outcomes, llm.provider, llm.model, llm.calls), encoding="utf-8")
    print(f"Transcript: {path.relative_to(ROOT)}")
    return 1 if any(o.error for o in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())
