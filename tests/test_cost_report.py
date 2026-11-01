"""The cost projection: token statistics, the arithmetic and the report (decision D-011)."""

import sys
from decimal import Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cost_report  # noqa: E402

from emporio.llm import DEFAULT_MODELS, DEFAULT_PROVIDER  # noqa: E402

PRICING = yaml.safe_load(cost_report.PRICING.read_text(encoding="utf-8"))
HAIKU = {"input": "0.10", "output": "0.50", "cache_write": "0.125", "cache_read": "0.01", "tool_prompt_tokens": 286}


def _record(input_tokens, output_tokens, calls=2, error=""):
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "calls": calls, "error": error}


def test_p90_is_the_nearest_rank():
    assert cost_report.p90(list(range(1, 11))) == 9
    assert cost_report.p90([7]) == 7
    assert cost_report.p90(list(range(1, 118))) == 106  # 117 values, as in three runs of the golden set


def test_tokens_leave_out_conversations_cut_by_a_provider_error():
    tokens = cost_report.measure([_record(1000, 100), _record(3000, 300, calls=4), _record(50, 0, error="HTTP 503")])
    assert tokens.conversations == 2
    assert (tokens.calls, tokens.input_mean, tokens.output_mean) == (3, 2000, 200)


def test_cost_per_conversation_is_exact():
    flash_lite = {"input": "0.30", "output": "2.50"}
    assert cost_report.conversation_cost(flash_lite, 6966, 156) == Decimal("0.0024798")


def test_projection_adds_the_tool_prompt_to_every_call():
    measured = cost_report.Tokens(117, Decimal(3), Decimal(7000), 12000, Decimal(150), 400)
    tokens = cost_report.projected(measured, HAIKU)
    assert (tokens.input_mean, tokens.input_p90, tokens.output_mean) == (7858, 12858, 150)


def test_caching_writes_the_prefix_once_and_reads_it_on_later_calls():
    tokens = cost_report.Tokens(117, Decimal(3), Decimal(10000), 15000, Decimal(100), 200)
    # 4,000 tokens at full price, 2,000 written, 2 x 2,000 read, 100 output tokens.
    assert cost_report.cached_conversation_cost(HAIKU, tokens, 2000) == Decimal("0.00074")


def test_monthly_cost_and_break_even():
    assert cost_report.monthly(Decimal("0.0025"), 100, 30) == Decimal("7.5")
    assert cost_report.break_even_per_day(Decimal(300), Decimal("0.001"), 30) == 10000
    assert cost_report.break_even_per_day(Decimal(301), Decimal("0.001"), 30) == 10034


def test_every_price_has_a_source_and_the_default_model_is_priced():
    priced = {f"{p['provider']}/{p['model']}" for p in PRICING["models"]}
    assert f"{DEFAULT_PROVIDER}/{DEFAULT_MODELS[DEFAULT_PROVIDER]}" in priced
    for price in PRICING["models"]:
        assert price["source"].startswith("https://")
        Decimal(price["input"]), Decimal(price["output"])  # prices are strings Decimal reads exactly


def test_report_from_the_evaluation_results():
    report = cost_report.build_report(PRICING, ROOT / "eval" / "results")
    assert report.startswith("# Cost projection\n")
    assert "| `gemini/gemini-3.5-flash-lite` | measured | 117 |" in report
    assert "`gemini/gemini-3.8-flash` is not projected" in report  # a partial run
    assert "R$ 5,4212" in report and "pays for itself above" in report
