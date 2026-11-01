"""The scenario file is well formed and the runner records turns, tools and corrections (decision D-009)."""

import importlib.util
import sys
from pathlib import Path

import yaml
from conftest import ScriptedLLM, text, tools

from emporio.config import agent_now

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("run_scenarios", ROOT / "eval" / "run_scenarios.py")
run_scenarios = importlib.util.module_from_spec(_spec)
sys.modules["run_scenarios"] = run_scenarios  # dataclasses look their module up while the script loads
_spec.loader.exec_module(run_scenarios)


def test_scenarios_are_well_formed():
    scenarios = yaml.safe_load((ROOT / "eval" / "scenarios.yaml").read_text(encoding="utf-8"))
    ids = [s["id"] for s in scenarios]
    assert len(ids) == len(set(ids)) >= 30
    for scenario in scenarios:
        assert set(scenario) <= {"id", "purpose", "turns", "now"}, scenario["id"]
        assert scenario["purpose"] and scenario["turns"]
        assert all(isinstance(turn, str) and turn.strip() for turn in scenario["turns"])
        agent_now(scenario.get("now", run_scenarios.DEFAULT_NOW))  # raises on a bad date
    assert [i for i in ids if i.startswith("brief_")] == [
        "brief_guitars_under_1000",
        "brief_store_address",
        "brief_takamine_price",
        "brief_regret_return",
    ]


def test_runner_records_turns_tools_and_corrections(store, manual, tmp_path):
    scenario = {"id": "demo", "purpose": "demo", "turns": ["Quanto custa o Takamine GD20?", "Obrigado!"]}
    llm = ScriptedLLM(
        tools(("search_products", {"query": "Takamine GD20"})),
        text("Custa R$ 1.999,00."),  # invented: corrected once
        text("Custa R$ 2.199,00."),
        text("De nada!"),
    )
    usage = run_scenarios.CountingUsage(tmp_path / "usage.jsonl")
    outcome = run_scenarios.run_scenario(llm, scenario, store, manual, tmp_path, usage)
    assert [(t.customer, t.tools, t.answer) for t in outcome.turns] == [
        ("Quanto custa o Takamine GD20?", ['search_products({"query": "Takamine GD20"})'], "Custa R$ 2.199,00."),
        ("Obrigado!", [], "De nada!"),
    ]
    assert outcome.corrections == 1 and not outcome.error
    markdown = run_scenarios.transcript([outcome], "scripted", "scripted-1", 4)
    assert "## demo" in markdown and "1 amount corrections" in markdown
    assert "- tool: `search_products" in markdown
