"""The example conversations: their definitions and the runner that writes them (decision D-011)."""

import sys
from pathlib import Path

import yaml
from conftest import ScriptedLLM, text, tools

from emporio.llm.base import LLMError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_examples  # noqa: E402

EXAMPLES = yaml.safe_load(run_examples.CONVERSATIONS.read_text(encoding="utf-8"))


def test_the_brief_asks_for_three_to_five_conversations():
    assert 3 <= len(EXAMPLES) <= 5
    for example in EXAMPLES:
        assert {"file", "title", "shows", "turns"} <= example.keys()
        assert len(example["turns"]) > 1  # every example is a conversation, not one question


def _runner(tmp_path, monkeypatch, llm):
    monkeypatch.setattr(run_examples, "EXAMPLES", tmp_path)
    monkeypatch.setattr(run_examples, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_examples, "create_client", lambda provider, model: llm)
    counting_usage = run_examples.CountingUsage
    monkeypatch.setattr(run_examples, "CountingUsage", lambda: counting_usage(tmp_path / "usage.jsonl"))


def test_an_example_shows_messages_tool_calls_results_and_answers(tmp_path, monkeypatch):
    llm = ScriptedLLM(
        tools(("search_products", {"query": "Yamaha C40"})),
        text("O Yamaha C40 custa R$ 599,90."),
        text("Posso ajudar com mais alguma coisa?"),
        text("Até logo!"),
    )
    _runner(tmp_path, monkeypatch, llm)
    assert run_examples.main(["--only", "01-guitars-and-payment"]) == 0
    written = (tmp_path / "01-guitars-and-payment.md").read_text(encoding="utf-8")
    assert written.startswith("# Guitars under R$ 1,000, then installments and Pix\n")
    assert "store clock at 23/03/2026 10:00 (segunda-feira)" in written and "not edited by hand" in written
    assert "**Cliente:** Quais violões vocês têm até R$ 1.000?" in written
    assert '<summary>tool: <code>search_products({"query": "Yamaha C40"})</code></summary>' in written
    assert '"price": "R$ 599,90"' in written  # the tool result, as the model read it
    assert "**Assistente:** O Yamaha C40 custa R$ 599,90." in written
    assert written.count("**Cliente:**") == written.count("**Assistente:**") == 3


def test_a_provider_error_writes_nothing(tmp_path, monkeypatch):
    _runner(tmp_path, monkeypatch, ScriptedLLM(LLMError("gemini RateLimitError: quota")))
    assert run_examples.main(["--only", "02-late-order"]) == 1
    assert not (tmp_path / "02-late-order.md").exists()
