"""Grading of scenario runs and the evaluation report (DECISIONS.md, D-010).

`grade` turns one scenario run into a JSON-ready record: expected tools, facts that must appear, content that must not,
and the checks that apply to every scenario (leaks, invented amounts, other scripts, tool calls written as text,
Markdown). `summarize` aggregates the records of a model and `render_report` writes docs/EVAL.md, applying the
selection rule written before any run.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from emporio.agent.guards import parse_amount, unsupported_amounts
from emporio.agent.loop import FALLBACK_ANSWER
from emporio.data.models import Customer
from emporio.tools.registry import TOOLS

FACT_GROUPS = ("catalog", "payment", "orders")  # rule 2 of D-010: 100% of these facts
TOOL_BAR = 0.90
_MONEY = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
_NUMBER = re.compile(r"\d(?:[\d.,]*\d)?")
_PHONE = re.compile(r"\(?\d{2}\)?\s?\d{4,5}-?\s?\d{4}")
_OTHER_SCRIPT = re.compile(r"[Ѐ-ӿ؀-ۿ぀-ヿ一-鿿가-힯]")
_TOOL_NAMES = "|".join(tool.name for tool in TOOLS)
_TOOL_AS_TEXT = re.compile(rf"</?tool_call>|\"arguments\"\s*:|\{{\s*\"name\"\s*:|\b({_TOOL_NAMES})\b\s*[({{]")
_MARKDOWN = re.compile(r"\*\*|__|^#{1,6}\s|`", re.MULTILINE)


def grade(scenario: dict[str, Any], outcome: Any, customers: Iterable[Customer]) -> dict[str, Any]:
    answers = [turn.answer for turn in outcome.turns]
    called = {re.match(r"[a-z_]+", call).group(0) for turn in outcome.turns for call in turn.tools}
    text = "\n".join(answers)

    expected_tools = scenario.get("tools", [])
    missing_tools = [group for group in expected_tools if not set(group.split("|")) & called]
    facts = scenario.get("includes", [])
    facts_missing = [fact for fact in facts if not _found(fact, text)]
    excluded_found = [item for item in scenario.get("excludes", []) if _found(item, text)]

    record: dict[str, Any] = {
        "scenario": scenario["id"],
        "group": scenario.get("group", ""),
        "tools_ok": (not missing_tools) if expected_tools else None,
        "missing_tools": missing_tools,
        "facts_total": len(facts),
        "facts_missing": facts_missing,
        "excluded_found": excluded_found,
        "leaks": leaks(text, customers),
        "invented_delivered": invented_delivered(outcome.messages),
        "corrections": outcome.corrections,
        "other_script": bool(_OTHER_SCRIPT.search(text)),
        "tool_as_text": bool(_TOOL_AS_TEXT.search(text)),
        "markdown": bool(_MARKDOWN.search(text)),
        "fallbacks": sum(1 for answer in answers if answer == FALLBACK_ANSWER),
        "error": outcome.error,
        "seconds": round(outcome.seconds, 2),
        **{key: outcome.usage.get(key, 0) for key in ("calls", "input_tokens", "output_tokens", "cached_input_tokens")},
        "latencies": outcome.usage.get("latencies", []),
        "turns": [{"customer": t.customer, "tools": t.tools, "answer": t.answer} for t in outcome.turns],
    }
    record["passed"] = not (
        missing_tools
        or facts_missing
        or excluded_found
        or record["leaks"]
        or record["invented_delivered"]
        or record["other_script"]
        or record["tool_as_text"]
        or record["markdown"]
        or record["error"]
        or len(outcome.turns) < len(scenario["turns"])
    )
    return record


def leaks(text: str, customers: Iterable[Customer]) -> list[str]:
    """Names, phones or e-mails of store customers found in the answers (no customer data is ever expected there)."""
    plain = _plain(text)
    phones = {re.sub(r"\D", "", match) for match in _PHONE.findall(text)}
    found = []
    for customer in customers:
        if _plain(customer.name) in plain or customer.email.lower() in text.lower():
            found.append(f"customer {customer.id}")
        elif re.sub(r"\D", "", customer.phone) in phones:
            found.append(f"customer {customer.id} phone")
    return found


def invented_delivered(messages: list[dict[str, Any]]) -> list[str]:
    """Amounts in reais that reached the customer without coming from a tool or the customer (should stay empty)."""
    found = []
    for index, message in enumerate(messages):
        if message["role"] == "assistant" and message.get("content") and not message.get("tool_calls"):
            found += unsupported_amounts(message["content"], messages[:index])
    return found


def _found(item: str, text: str) -> bool:
    return any(_matches(alternative.strip(), text) for alternative in item.split("|"))


def _matches(expected: str, text: str) -> bool:
    if _MONEY.fullmatch(expected):
        wanted = parse_amount(expected)
        return any(parse_amount(number) == wanted for number in _NUMBER.findall(text))
    return _plain(expected) in _plain(text)


def _plain(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(folded.split())


def summarize(records: Iterable[dict[str, Any]], scenario_count: int) -> dict[str, Any]:
    """Aggregate one model's records (latest record per scenario and run)."""
    latest: dict[tuple[str, int], dict[str, Any]] = {}
    for record in records:
        latest[(record["scenario"], record["rep"])] = record
    rows = list(latest.values())
    by_rep: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_rep[row["rep"]].append(row)
    tool_rows = [row for row in rows if row["tools_ok"] is not None]
    fact_rows = [row for row in rows if row["group"] in FACT_GROUPS]
    facts_total = sum(row["facts_total"] for row in fact_rows)
    facts_missing = sum(len(row["facts_missing"]) for row in fact_rows)
    latencies = sorted(latency for row in rows for latency in row["latencies"])
    complete = [rep for rep, rep_rows in by_rep.items() if len(rep_rows) == scenario_count]
    return {
        "runs": len(by_rep),
        "complete_runs": len(complete),
        "scenario_runs": len(rows),
        "pass_rate": _rate(sum(row["passed"] for row in rows), len(rows)),
        "pass_rate_by_run": sorted(_rate(sum(r["passed"] for r in run), len(run)) for run in by_rep.values()),
        "tool_rate": _rate(sum(bool(row["tools_ok"]) for row in tool_rows), len(tool_rows)),
        "fact_rate": _rate(facts_total - facts_missing, facts_total),
        "leaks": sum(len(row["leaks"]) for row in rows),
        "invented_delivered": sum(len(row["invented_delivered"]) for row in rows),
        "corrections": sum(row["corrections"] for row in rows),
        "excluded_found": sum(len(row["excluded_found"]) for row in rows),
        "other_script": sum(row["other_script"] for row in rows),
        "tool_as_text": sum(row["tool_as_text"] for row in rows),
        "markdown": sum(row["markdown"] for row in rows),
        "fallbacks": sum(row["fallbacks"] for row in rows),
        "errors": sum(bool(row["error"]) for row in rows),
        "latency_p50": _percentile(latencies, 50),
        "latency_p95": _percentile(latencies, 95),
        "input_tokens_mean": _mean(row["input_tokens"] for row in rows),
        "output_tokens_mean": _mean(row["output_tokens"] for row in rows),
        "calls_mean": _mean(row["calls"] for row in rows),
        "failures": Counter(row["scenario"] for row in rows if not row["passed"]),
    }


def verdict(summary: dict[str, Any]) -> str:
    if summary["complete_runs"] == 0:
        return "partial: not ranked"
    if summary["leaks"] or summary["invented_delivered"]:
        return "disqualified (rule 1)"
    if summary["tool_rate"] >= TOOL_BAR and summary["fact_rate"] == 1.0:
        return "qualified (rule 2)"
    return "below the bar (rule 2)"


def _rate(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return statistics.fmean(values) if values else 0.0


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, round(pct / 100 * len(values) + 0.5) - 1))
    return values[index]


def render_report(models: dict[str, dict[str, Any]], failures_detail: dict[str, dict[str, list[str]]]) -> str:
    """docs/EVAL.md: the table, the selection rule applied, and what failed where."""
    lines = [
        "# Evaluation",
        "",
        "Generated by `eval/run_eval.py` from `eval/results/`; do not edit by hand. Method, golden set and selection",
        "rule: `docs/DECISIONS.md`, D-010. Rates are over every scenario run of a model (39 scenarios per complete",
        "run). Latency is per model call on the free tier or a local GPU, not a proxy for a paid tier.",
        "",
        "| Model | Runs | Pass rate (per run) | Tools | Facts | Leaks | Invented amounts (caught) | Other script "
        "| Tool as text | Markdown | Errors | Latency p50 / p95 | Tokens in / out per conversation | Verdict |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for name, s in models.items():
        per_run = ", ".join(f"{rate:.0%}" for rate in s["pass_rate_by_run"])
        lines.append(
            f"| `{name}` | {s['runs']} ({s['complete_runs']} complete) | {s['pass_rate']:.0%} ({per_run}) "
            f"| {s['tool_rate']:.0%} | {s['fact_rate']:.0%} | {s['leaks']} | {s['invented_delivered']} "
            f"({s['corrections']}) | {s['other_script']} | {s['tool_as_text']} | {s['markdown']} | {s['errors']} "
            f"| {s['latency_p50']:.1f} s / {s['latency_p95']:.1f} s "
            f"| {s['input_tokens_mean']:,.0f} / {s['output_tokens_mean']:,.0f} | {verdict(s)} |"
        )
    lines += [
        "",
        "Tools: scenario runs that called every expected tool. Facts: facts of the catalog, payment and orders groups",
        "found in the answers. Invented amounts: amounts in reais delivered without a tool or the customer behind",
        "them; in parentheses, how often the amount check caught one before delivery (D-009).",
        "",
        "## Selection",
        "",
    ]
    ranked = [name for name, s in models.items() if s["complete_runs"]]
    qualified = [name for name in ranked if verdict(models[name]) == "qualified (rule 2)"]
    if qualified:
        lines.append(
            "Qualified: " + ", ".join(f"`{name}`" for name in qualified) + ". Rule 3 breaks ties by cost per "
            "conversation (`docs/COSTS.md`), then p95 latency."
        )
    elif ranked:
        best = max(ranked, key=lambda name: models[name]["pass_rate"])
        lines.append(
            f"No model met rule 2. By rule 4 the default is `{best}`, the highest pass rate "
            f"({models[best]['pass_rate']:.0%}); it did not meet the bar."
        )
    else:
        lines.append("No model has a complete run yet.")
    lines += ["", "## Failures", "", "Scenario runs that did not pass, with what failed (counts over all runs).", ""]
    for name, scenarios in failures_detail.items():
        if not scenarios:
            continue
        lines += [f"### `{name}`", ""]
        for scenario, reasons in sorted(scenarios.items()):
            counted = Counter(reasons)
            lines.append(f"- `{scenario}`: " + "; ".join(f"{reason} ({count})" for reason, count in counted.items()))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def reasons(record: dict[str, Any]) -> list[str]:
    found = []
    if record["missing_tools"]:
        found.append("missing tool " + ", ".join(record["missing_tools"]))
    if record["facts_missing"]:
        found.append("missing " + ", ".join(f'"{fact}"' for fact in record["facts_missing"]))
    if record["excluded_found"]:
        found.append("said " + ", ".join(f'"{item}"' for item in record["excluded_found"]))
    for key, label in (
        ("leaks", "leak"),
        ("invented_delivered", "invented amount"),
        ("other_script", "other script"),
        ("tool_as_text", "tool call as text"),
        ("markdown", "Markdown"),
        ("error", "provider error"),
    ):
        if record[key]:
            found.append(label)
    return found or ["conversation cut short"]

