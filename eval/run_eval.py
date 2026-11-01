"""Run the golden set on one model, grade every scenario and rewrite docs/EVAL.md (DECISIONS.md, D-010).

Each scenario run becomes one line in eval/results/<provider>-<model>.jsonl. A run can be stopped and resumed: scenario
runs already graded without a provider error are skipped. Three provider errors in a row stop the run (a spent daily
quota fails every call after it). The report is rebuilt from every results file at the end, or alone with --report.

Usage:
    python eval/run_eval.py --provider ollama --reps 3
    python eval/run_eval.py --provider gemini --model gemini-3.5-flash-lite --reps 3 --min-interval 4.5
    python eval/run_eval.py --provider gemini --model gemini-3.8-flash --only brief_takamine_price,complaint
    python eval/run_eval.py --report
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import yaml
from dotenv import load_dotenv

import grading
from run_scenarios import ROOT, SCENARIOS, CountingUsage, Throttled, run_scenario

from emporio.data.loader import load_store_data
from emporio.data.memory import InMemoryStore
from emporio.data.policy import load_policy_manual
from emporio.llm import PROVIDERS, create_client, redact
from emporio.llm.base import LLMError

RESULTS = ROOT / "eval" / "results"
REPORT = ROOT / "docs" / "EVAL.md"
MAX_ERRORS_IN_A_ROW = 3


def results_path(provider: str, model: str) -> Path:
    return RESULTS / (re.sub(r"[^A-Za-z0-9.]+", "-", f"{provider}-{model}") + ".jsonl")


def read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def write_report(scenario_count: int) -> Path:
    models, failures = {}, {}
    for path in sorted(RESULTS.glob("*.jsonl")):
        records = read_records(path)
        if not records:
            continue
        name = f"{records[0]['provider']} / {records[0]['model']}"
        models[name] = grading.summarize(records, scenario_count)
        latest = {(r["scenario"], r["rep"]): r for r in records}
        detail: dict[str, list[str]] = defaultdict(list)
        for record in latest.values():
            if not record["passed"]:
                detail[record["scenario"]] += grading.reasons(record)
        failures[name] = dict(detail)
    REPORT.write_text(grading.render_report(models, failures), encoding="utf-8")
    return REPORT


def _shown(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=PROVIDERS)
    parser.add_argument("--model")
    parser.add_argument("--reps", type=int, default=1, help="how many full runs to complete (default 1)")
    parser.add_argument("--only", help="comma-separated scenario ids (a partial run)")
    parser.add_argument("--min-interval", type=float, default=0.0, help="seconds between model calls")
    parser.add_argument("--report", action="store_true", help="only rebuild docs/EVAL.md from eval/results/")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    scenarios = yaml.safe_load(SCENARIOS.read_text(encoding="utf-8"))
    scenario_count = len(scenarios)  # a complete run covers all of them, even when --only runs a few
    if args.report:
        print(f"Report: {_shown(write_report(scenario_count))}")
        return 0
    if not args.provider:
        parser.error("--provider is required unless --report is given")

    load_dotenv(ROOT / ".env")
    try:
        llm = Throttled(create_client(args.provider, args.model), args.min_interval)
    except LLMError as error:
        print(redact(str(error)))
        return 2
    if args.only:
        wanted = set(args.only.split(","))
        scenarios = [s for s in scenarios if s["id"] in wanted]

    path = results_path(llm.provider, llm.model)
    done = {(r["scenario"], r["rep"]) for r in read_records(path) if not r["error"]}
    store, manual = InMemoryStore.from_csv(), load_policy_manual()
    customers = load_store_data().customers
    usage = CountingUsage()
    errors_in_a_row = 0
    RESULTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tickets_dir, path.open("a", encoding="utf-8") as results:
        for rep in range(1, args.reps + 1):
            for scenario in scenarios:
                if (scenario["id"], rep) in done:
                    continue
                outcome = run_scenario(llm, scenario, store, manual, Path(tickets_dir), usage)
                record = grading.grade(scenario, outcome, customers)
                record.update(provider=llm.provider, model=llm.model, rep=rep)
                results.write(json.dumps(record, ensure_ascii=False) + "\n")
                results.flush()
                status = "ERROR" if record["error"] else ("pass" if record["passed"] else "FAIL")
                print(f"run {rep} {status:5} {scenario['id']} ({record['seconds']:.1f} s)", flush=True)
                errors_in_a_row = errors_in_a_row + 1 if record["error"] else 0
                if errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
                    print(f"Stopped after {MAX_ERRORS_IN_A_ROW} provider errors in a row: {record['error']}")
                    write_report(scenario_count)
                    return 1
    print(f"Results: {_shown(path)}")
    print(f"Report: {_shown(write_report(scenario_count))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
