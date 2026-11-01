"""The scenario file and the transcript runner (decisions D-009 and D-010)."""

import json
import re
import sys
from pathlib import Path

import yaml
from conftest import ScriptedLLM, text, tools

from emporio.config import agent_now
from emporio.tools.registry import TOOLS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import run_scenarios  # noqa: E402  (a script folder, not a package)

GROUPS = {"catalog", "payment", "orders", "policy", "returns", "scope"}
SCENARIOS = yaml.safe_load((ROOT / "eval" / "scenarios.yaml").read_text(encoding="utf-8"))


def test_scenarios_are_well_formed():
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids)) >= 30
    tool_names = {tool.name for tool in TOOLS}
    for scenario in SCENARIOS:
        assert set(scenario) <= {"id", "purpose", "group", "turns", "now", "tools", "includes", "excludes"}, scenario
        assert scenario["purpose"] and scenario["group"] in GROUPS, scenario["id"]
        assert all(isinstance(turn, str) and turn.strip() for turn in scenario["turns"])
        for group in scenario.get("tools", []):
            assert set(group.split("|")) <= tool_names, (scenario["id"], group)
        for item in scenario.get("includes", []) + scenario.get("excludes", []):
            assert isinstance(item, str) and item.strip(), scenario["id"]
        assert scenario.get("includes") or scenario.get("excludes"), f"{scenario['id']} has no expectation"
        agent_now(scenario.get("now", run_scenarios.DEFAULT_NOW))  # raises on a bad date
    assert [i for i in ids if i.startswith("brief_")] == [
        "brief_guitars_under_1000",
        "brief_store_address",
        "brief_takamine_price",
        "brief_regret_return",
    ]


def test_runner_records_turns_tools_corrections_and_usage(store, manual, tmp_path):
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
    assert (outcome.usage["calls"], outcome.usage["input_tokens"], len(outcome.usage["latencies"])) == (4, 400, 4)
    assert [m["role"] for m in outcome.messages] == ["user", "assistant", "tool", "assistant", "user", "assistant"]
    markdown = run_scenarios.transcript([outcome], "scripted", "scripted-1", 4)
    assert "## demo" in markdown and "1 amount corrections" in markdown
    assert "- tool: `search_products" in markdown
    assert json.dumps(outcome.usage)  # JSON-ready for the results file
    assert re.search(r"\(\d+\.\d s\)", markdown)
