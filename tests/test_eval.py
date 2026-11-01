"""Golden set facts, grading checks, the selection rule and the evaluation runner (decision D-010)."""

import json
import re
import sys
from pathlib import Path

import pytest
import yaml
from conftest import ScriptedLLM, text, tools

from emporio.agent.loop import FALLBACK_ANSWER
from emporio.data.loader import load_store_data
from emporio.tools.catalog import get_product_details, search_products
from emporio.tools.orders import get_order_status
from emporio.tools.payments import quote_payment
from emporio.tools.policy_tools import get_store_policy
from emporio.tools.returns import check_return_options

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import grading  # noqa: E402
import run_eval  # noqa: E402
from run_scenarios import Outcome, Turn  # noqa: E402

SCENARIOS = {s["id"]: s for s in yaml.safe_load((ROOT / "eval" / "scenarios.yaml").read_text(encoding="utf-8"))}
CUSTOMERS = load_store_data().customers


def _items(*ids):
    return [{"product_id": product_id, "quantity": 1} for product_id in ids]


# What the tools return for each scenario whose facts are numbers or dates: every such fact must come from here.
ORACLES = {
    "brief_guitars_under_1000": lambda ctx: search_products(ctx, category="violões", max_price=1000),
    "brief_takamine_price": lambda ctx: search_products(ctx, query="Takamine GD20"),
    "brief_regret_return": lambda ctx: check_return_options(ctx, "regret", "online", None, "2026-03-20"),
    "last_units_no_reservation": lambda ctx: get_product_details(ctx, product_id=136),
    "contradictory_description_hidden": lambda ctx: get_product_details(ctx, product_id=135),
    "active_promotion": lambda ctx: search_products(ctx, query="Ohana CK-20"),
    "expired_promotion": lambda ctx: get_product_details(ctx, product_id=102),
    "installments_then_pix": lambda ctx: [
        quote_payment(ctx, _items(95), "credit", 12),
        quote_payment(ctx, _items(95), "pix"),
    ],
    "cart_of_two_products": lambda ctx: quote_payment(ctx, _items(81, 127), "credit", 6),
    "minimum_installment": lambda ctx: quote_payment(ctx, _items(119), "credit", 6),
    "pix_over_promotion": lambda ctx: quote_payment(ctx, _items(94), "pix"),
    "payment_methods": lambda ctx: get_store_policy(ctx, "payment"),
    "order_late_delivery": lambda ctx: get_order_status(ctx, 8, "7821"),
    "order_asks_for_verification": lambda ctx: get_order_status(ctx, 3, "9012"),
    "defect_after_30_days": lambda ctx: check_return_options(ctx, "defect", "in_store", "2026-01-10"),
    "preference_exchange_in_store": lambda ctx: check_return_options(ctx, "preference", "in_store", "2026-03-21"),
    "regret_after_deadline": lambda ctx: check_return_options(ctx, "regret", "online", None, "2026-03-10"),
}
_CHECKABLE = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d{2}/\d{2}|BR[A-Z0-9]{9}BR")


def _checkable(item):
    return [alternative for alternative in item.split("|") if _CHECKABLE.fullmatch(alternative.strip())]


def test_every_money_date_and_code_fact_comes_from_the_tools(ctx, store):
    ctx.seen_products.update(product.id for product in store.list_products())
    for scenario_id, scenario in SCENARIOS.items():
        checkable = [item for item in scenario.get("includes", []) if _checkable(item)]
        if not checkable:
            continue
        assert scenario_id in ORACLES, f"{scenario_id} has facts without an oracle"
        output = json.dumps(ORACLES[scenario_id](ctx), ensure_ascii=False)
        for item in checkable:
            assert any(grading._found(alt, output) for alt in _checkable(item)), (scenario_id, item)


def _outcome(*answers, tools_called=(), messages=None, error=""):
    turns = [Turn(f"pergunta {i}", list(tools_called) if i == 0 else [], answer) for i, answer in enumerate(answers)]
    return Outcome(
        scenario={},
        turns=turns,
        error=error,
        messages=messages or [],
        usage={"calls": 2, "input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 0, "latencies": [0.5, 1.0]},
    )


SCENARIO = {
    "id": "demo",
    "group": "payment",
    "turns": ["pergunta"],
    "tools": ["search_products|get_product_details", "quote_payment"],
    "includes": ["2.089,05", "pix"],
    "excludes": ["carrinho"],
}
QUOTED = ['search_products({"query": "Takamine"})', 'quote_payment({"items": []})']


def test_a_correct_answer_passes():
    record = grading.grade(SCENARIO, _outcome("No Pix fica R$ 2089.05.", tools_called=QUOTED), CUSTOMERS)
    assert record["passed"] and record["tools_ok"] and record["facts_missing"] == []
    assert (record["calls"], record["input_tokens"], record["latencies"]) == (2, 100, [0.5, 1.0])


@pytest.mark.parametrize(
    "answer, called, failed",
    [
        ("No Pix fica R$ 2.089,05.", QUOTED[:1], "missing_tools"),
        ("No Pix fica R$ 2.199,00.", QUOTED, "facts_missing"),
        ("No Pix fica R$ 2.089,05. Coloquei no carrinho.", QUOTED, "excluded_found"),
        ("No Pix fica R$ 2.089,05. Ligue para Lucas Mendes da Silva.", QUOTED, "leaks"),
        ("No Pix fica R$ 2.089,05, fale com (67) 99812-3456.", QUOTED, "leaks"),
        ("No Pix fica R$ 2.089,05. 我们", QUOTED, "other_script"),
        ('No Pix fica R$ 2.089,05. quote_payment({"items": []})', QUOTED, "tool_as_text"),
        ("No **Pix** fica R$ 2.089,05.", QUOTED, "markdown"),
    ],
)
def test_each_check_fails_a_scenario(answer, called, failed):
    record = grading.grade(SCENARIO, _outcome(answer, tools_called=called), CUSTOMERS)
    assert not record["passed"]
    assert record[failed]


def test_invented_amounts_that_reached_the_customer_are_counted():
    messages = [
        {"role": "user", "content": "quanto custa?"},
        {"role": "tool", "tool_call_id": "c", "name": "quote_payment", "content": '{"pix_price": "R$ 2.089,05"}'},
        {"role": "assistant", "content": "No Pix fica R$ 1.999,00."},
    ]
    record = grading.grade(SCENARIO, _outcome("No Pix fica R$ 2.089,05.", tools_called=QUOTED, messages=messages),
                           CUSTOMERS)
    assert record["invented_delivered"] == ["R$ 1.999,00"] and not record["passed"]


def test_fallbacks_and_cut_conversations_are_visible():
    record = grading.grade({**SCENARIO, "turns": ["a", "b"]}, _outcome(FALLBACK_ANSWER, tools_called=QUOTED), CUSTOMERS)
    assert record["fallbacks"] == 1 and not record["passed"]
    assert "conversation cut short" in grading.reasons({**record, "facts_missing": [], "missing_tools": []})


def _record(scenario, rep, passed=True, group="payment", leaks=(), invented=(), tools_ok=True, facts_missing=()):
    return {
        "scenario": scenario, "rep": rep, "group": group, "passed": passed, "tools_ok": tools_ok,
        "missing_tools": [], "facts_total": 2, "facts_missing": list(facts_missing), "excluded_found": [],
        "leaks": list(leaks), "invented_delivered": list(invented), "corrections": 0, "other_script": False,
        "tool_as_text": False, "markdown": False, "fallbacks": 0, "error": "", "calls": 2, "input_tokens": 100,
        "output_tokens": 20, "latencies": [1.0, 2.0],
    }


def test_selection_rule():
    perfect = [_record("a", 1), _record("b", 1)]
    assert grading.verdict(grading.summarize(perfect, 2)) == "qualified (rule 2)"
    leaky = perfect + [_record("a", 2, leaks=["customer 1"])]
    assert grading.verdict(grading.summarize(leaky, 2)) == "disqualified (rule 1)"
    missing_fact = [_record("a", 1, passed=False, facts_missing=["2.089,05"]), _record("b", 1)]
    assert grading.verdict(grading.summarize(missing_fact, 2)) == "below the bar (rule 2)"
    assert grading.verdict(grading.summarize([_record("a", 1)], 2)) == "partial: not ranked"
    # A resumed scenario run replaces the failed one.
    resumed = [_record("a", 1, passed=False), _record("a", 1), _record("b", 1)]
    assert grading.summarize(resumed, 2)["pass_rate"] == 1.0


def test_report_applies_rule_4_when_no_model_qualifies():
    weak = grading.summarize([_record("a", 1, passed=False, tools_ok=False), _record("b", 1)], 2)
    weaker = grading.summarize([_record("a", 1, passed=False, tools_ok=False), _record("b", 1, passed=False)], 2)
    report = grading.render_report({"m1": weak, "m2": weaker}, {"m1": {"a": ["missing tool quote_payment"]}})
    assert "By rule 4 the default is `m1`" in report
    assert "- `a`: missing tool quote_payment (1)" in report


def test_runner_resumes_and_writes_the_report(tmp_path, monkeypatch):
    monkeypatch.setattr(run_eval, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(run_eval, "REPORT", tmp_path / "EVAL.md")
    monkeypatch.setattr(run_eval, "NOTES", tmp_path / "notes.md")
    (tmp_path / "notes.md").write_text("## Notes\n\nRead by hand.\n", encoding="utf-8")
    monkeypatch.setattr(run_eval, "load_dotenv", lambda *a, **k: None)
    llm = ScriptedLLM(tools(("search_products", {"query": "Takamine GD20"})), text("Custa R$ 2.199,00."))
    monkeypatch.setattr(run_eval, "create_client", lambda provider, model: llm)
    counting_usage = run_eval.CountingUsage
    monkeypatch.setattr(run_eval, "CountingUsage", lambda: counting_usage(tmp_path / "usage.jsonl"))
    assert run_eval.main(["--provider", "ollama", "--only", "brief_takamine_price"]) == 0
    [record] = run_eval.read_records(tmp_path / "results" / "scripted-scripted-1.jsonl")
    assert record["passed"] and record["rep"] == 1
    report = (tmp_path / "EVAL.md").read_text(encoding="utf-8")
    assert "partial: not ranked" in report and report.endswith("Read by hand.\n")
    # Resuming skips the finished scenario run: no model call is made.
    assert run_eval.main(["--provider", "ollama", "--only", "brief_takamine_price"]) == 0
    assert len(llm.calls) == 2


def test_behaviour_is_needed_to_pass_but_is_not_a_fact():
    scenario = {**SCENARIO, "says": ["desculp"]}
    record = grading.grade(scenario, _outcome("No Pix fica R$ 2.089,05.", tools_called=QUOTED), CUSTOMERS)
    assert record["says_missing"] == ["desculp"] and not record["passed"]
    assert record["facts_missing"] == []  # the fact rate of rule 2 is untouched
    assert "did not say" in grading.reasons(record)[0]


def test_symbols_erased_by_accent_folding_do_not_match_every_answer():
    # "°C" folded to "c" and failed the first weather answer that had no temperature at all.
    assert not grading._found("°C", "Não sei sobre o tempo, mas posso ajudar com instrumentos.")
    assert grading._found("°C", "Amanhã faz 30°C.")


def test_regrade_applies_new_expectations_to_stored_answers():
    record = grading.grade(SCENARIO, _outcome("No Pix fica R$ 2.089,05.", tools_called=QUOTED), CUSTOMERS)
    record.update(provider="p", model="m", rep=2, invented_delivered=["R$ 1,00"])
    stricter = {**SCENARIO, "includes": ["2.089,05", "pix", "boleto"]}
    regraded = grading.regrade(record, stricter, CUSTOMERS)
    assert regraded["facts_missing"] == ["boleto"]
    assert (regraded["rep"], regraded["invented_delivered"], regraded["calls"]) == (2, ["R$ 1,00"], 2)
