"""Project the agent's cost per conversation and per month from the evaluation's measured tokens (DECISIONS.md, D-011).

Tokens per conversation come from eval/results/ (one record per scenario run, provider errors left out); prices, the
exchange rate, the volumes and the GPU machine come from scripts/pricing.yaml. All arithmetic is in Decimal. Writes
docs/COSTS.md.

Usage:
    python scripts/cost_report.py
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from run_eval import read_records, results_path  # noqa: E402

from emporio.llm import DEFAULT_MODELS, DEFAULT_PROVIDER  # noqa: E402
from emporio.tools.base import brl  # noqa: E402

PRICING = ROOT / "scripts" / "pricing.yaml"
REPORT = ROOT / "docs" / "COSTS.md"
MILLION = Decimal(1_000_000)
FULL_RUN = 39  # scenarios in the golden set: fewer complete conversations than one run are not projected


@dataclass(frozen=True)
class Tokens:
    conversations: int
    calls: Decimal  # mean model calls per conversation
    input_mean: Decimal
    input_p90: int
    output_mean: Decimal
    output_p90: int


def p90(values: list[int]) -> int:
    """Nearest rank: the smallest value with at least 90% of the values at or below it."""
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * 0.9) - 1]


def measure(records: list[dict[str, Any]]) -> Tokens:
    done = [r for r in records if not r["error"]]
    inputs, outputs = [r["input_tokens"] for r in done], [r["output_tokens"] for r in done]
    count = Decimal(len(done)) if done else Decimal(1)
    return Tokens(
        conversations=len(done),
        calls=sum(Decimal(r["calls"]) for r in done) / count,
        input_mean=Decimal(sum(inputs)) / count,
        input_p90=p90(inputs) if done else 0,
        output_mean=Decimal(sum(outputs)) / count,
        output_p90=p90(outputs) if done else 0,
    )


def projected(tokens: Tokens, price: dict[str, Any]) -> Tokens:
    """Another model's tokens plus what the API adds to every request with tools."""
    extra = Decimal(price.get("tool_prompt_tokens", 0))
    return Tokens(
        tokens.conversations,
        tokens.calls,
        tokens.input_mean + extra * tokens.calls,
        tokens.input_p90 + int(extra * tokens.calls),
        tokens.output_mean,
        tokens.output_p90,
    )


def conversation_cost(price: dict[str, Any], input_tokens: Decimal | int, output_tokens: Decimal | int) -> Decimal:
    return (Decimal(input_tokens) * Decimal(price["input"]) + Decimal(output_tokens) * Decimal(price["output"])) / MILLION


def cached_conversation_cost(price: dict[str, Any], tokens: Tokens, prefix: int) -> Decimal:
    """The prefix is written to the cache on the first call and read on every later call of the conversation."""
    prefix_tokens = Decimal(prefix)
    full_price = tokens.input_mean - prefix_tokens * tokens.calls
    return (
        full_price * Decimal(price["input"])
        + prefix_tokens * Decimal(price["cache_write"])
        + prefix_tokens * (tokens.calls - 1) * Decimal(price["cache_read"])
        + tokens.output_mean * Decimal(price["output"])
    ) / MILLION


def monthly(cost: Decimal, per_day: int, days: int) -> Decimal:
    return cost * per_day * days


def break_even_per_day(machine_monthly: Decimal, cost: Decimal, days: int) -> int:
    """Conversations a day at which a month of API calls costs as much as the machine."""
    return math.ceil(machine_monthly / (cost * days))


def usd(value: Decimal, places: int = 2) -> str:
    return f"US$ {value:,.{places}f}"


def money(value: Decimal, rate: Decimal) -> str:
    return f"{usd(value)} ({brl(value * rate)})"


def build_report(pricing: dict[str, Any], results_dir: Path) -> str:
    rate = Decimal(pricing["exchange_rate"]["usd_brl"])
    days, volumes = pricing["days_per_month"], pricing["volumes_per_day"]

    def tokens_of(name: str) -> Tokens:
        provider, model = name.split("/", 1)
        path = results_dir / results_path(provider, model).name
        return measure(read_records(path))

    rows, costs, notes = [], [], []
    for price in pricing["models"]:
        name = f"{price['provider']}/{price['model']}"
        if "tokens_from" in price:
            tokens = projected(tokens_of(price["tokens_from"]), price)
            source = f"projected from `{price['tokens_from']}`"
        else:
            tokens = tokens_of(name)
            source = "measured"
        rows.append((name, source, tokens))
        if tokens.conversations < FULL_RUN:
            notes.append(
                f"`{name}` is not projected: {tokens.conversations} complete conversations, fewer than one run of "
                "the golden set."
            )
            continue
        mean = conversation_cost(price, tokens.input_mean, tokens.output_mean)
        cached = cached_conversation_cost(price, tokens, pricing["prefix_tokens"]) if "cache_write" in price else None
        costs.append((name, price, tokens, mean, cached))
    for name in pricing["local"]["models"]:
        rows.append((name, "measured (local)", tokens_of(name)))

    lines = [
        "# Cost projection",
        "",
        "Generated by `scripts/cost_report.py` from `eval/results/` and `scripts/pricing.yaml`; do not edit by hand.",
        "Method: `docs/DECISIONS.md`, D-011. Prices are the paid tier's, in USD per million tokens, read on "
        f"{pricing['retrieved']}. 1 USD = R$ {str(rate).replace('.', ',')} ({pricing['exchange_rate']['source']}).",
        "",
        "## Tokens per conversation",
        "",
        "A conversation is one scenario run of the golden set (1 to 4 customer messages, several model calls); each "
        "model call resends the system prompt, the tool definitions and the history.",
        "",
        "| Model | Tokens | Conversations | Model calls (mean) | Input (mean / p90) | Output (mean / p90) |",
        "|---|---|---:|---:|---|---|",
    ]
    for name, source, tokens in rows:
        lines.append(
            f"| `{name}` | {source} | {tokens.conversations} | {tokens.calls:.1f} | "
            f"{tokens.input_mean:,.0f} / {tokens.input_p90:,} | {tokens.output_mean:,.0f} / {tokens.output_p90:,} |"
        )

    lines += [
        "",
        "## Cost per conversation",
        "",
        "| Model | Price in / out | Mean | p90 | Mean with prompt caching |",
        "|---|---|---:|---:|---:|",
    ]
    for name, price, tokens, mean, cached in costs:
        p90_cost = conversation_cost(price, tokens.input_p90, tokens.output_p90)
        lines.append(
            f"| `{name}` | {price['input']} / {price['output']} | {usd(mean, 5)} | {usd(p90_cost, 5)} | "
            f"{usd(cached, 5) if cached is not None else 'not projected'} |"
        )

    header = " | ".join(f"{volume} a day" for volume in volumes)
    lines += [
        "",
        f"## Monthly cost ({days} days, mean conversation)",
        "",
        f"| Model | {header} |",
        "|---|" + "---:|" * len(volumes),
    ]
    for name, _, _, mean, cached in costs:
        cells = " | ".join(money(monthly(mean, volume, days), rate) for volume in volumes)
        lines.append(f"| `{name}` | {cells} |")
        if cached is not None:
            cells = " | ".join(money(monthly(cached, volume, days), rate) for volume in volumes)
            lines.append(f"| `{name}` with prompt caching | {cells} |")

    local = pricing["local"]
    machine = Decimal(local["hourly"]) * local["hours_per_month"]
    default = f"{DEFAULT_PROVIDER}/{DEFAULT_MODELS[DEFAULT_PROVIDER]}"
    default_cost = next(mean for name, _, _, mean, _ in costs if name == default)
    lines += [
        "",
        "## A local model on a rented GPU",
        "",
        f"{local['machine']}: {usd(Decimal(local['hourly']), 3)} an hour, {local['hours_per_month']} hours a month, "
        f"{money(machine, rate)} a month whatever the volume. Against the default model, `{default}`, at "
        f"{usd(default_cost, 5)} a conversation, the machine pays for itself above "
        f"{break_even_per_day(machine, default_cost, days):,} conversations a day. No local model met the bar of the "
        "evaluation (`docs/EVAL.md`), and the throughput of a T4 was not measured.",
        "",
        "## Notes",
        "",
    ]
    for price in pricing["models"]:
        name = f"`{price['provider']}/{price['model']}`"
        if "caching" in price:
            lines.append(f"- {name}, prompt caching: {price['caching']}")
        if "note" in price:
            lines.append(f"- {name}: {price['note']}")
    lines += [f"- {note}" for note in notes]
    lines += [
        "- Claude Haiku 5.5 was not measured (no API credit): its tokens are Gemini Flash-Lite's plus the "
        "tool-use system prompt the API adds to every request. Claude's tokenizer counts the same text differently, "
        "and its adaptive thinking adds output tokens that could not be measured here.",
        "- Gemini's OpenAI-compatible endpoint reports thinking only in `total_tokens`, and the evaluation recorded "
        "`completion_tokens`. In 8 later calls of the agent Flash-Lite used no thinking at its default level, so its "
        "output is taken as complete; the adapter now counts thinking as output.",
        "- Prompt caching, where projected, covers only the system prompt and tool definitions on calls after the "
        "first in a conversation; the history can also be cached, so the real saving can be larger.",
        "- Prices change: regenerate after updating `scripts/pricing.yaml`. Sources:",
    ]
    lines += [f"  - `{p['provider']}/{p['model']}`: {p['source']}" for p in pricing["models"]]
    lines += [f"  - GPU machine: {local['source']}", f"  - Exchange rate: {pricing['exchange_rate']['url']}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    pricing = yaml.safe_load(PRICING.read_text(encoding="utf-8"))
    REPORT.write_text(build_report(pricing, ROOT / "eval" / "results"), encoding="utf-8")
    print(f"Report: {REPORT.relative_to(ROOT) if REPORT.is_relative_to(ROOT) else REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
