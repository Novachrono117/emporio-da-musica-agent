"""Amount check, correction in the loop, system prompt and greeting (decision D-009)."""

import json
from datetime import datetime

import pytest
from conftest import MONDAY_10AM, ScriptedLLM, text, tools

from emporio.agent.guards import unsupported_amounts
from emporio.agent.loop import FALLBACK_ANSWER, Agent
from emporio.agent.memory import new_session
from emporio.agent.prompts import GREETING, system_prompt
from emporio.agent.usage import UsageLog
from emporio.config import STORE_TZ

QUOTE = {
    "cash_price": "R$ 2.199,00",
    "pix_price": "R$ 2.089,05",
    "installments": {"text": "12x de R$ 183,25 sem juros"},
}
TOOL_RESULT = {"role": "tool", "tool_call_id": "c", "name": "quote_payment", "content": json.dumps(QUOTE)}


@pytest.mark.parametrize(
    "answer",
    [
        "Sai por R$ 2.199,00 ou R$ 2.089,05 no Pix.",
        "Custa R$2199 à vista.",  # no separator, no cents
        "Custa R$ 2.199 à vista.",  # thousands only
        "São 12x de R$ 183,25.",
        "Custa R$ 2199.00.",  # English decimal point, as Qwen writes
        "Custa R$ 2,199.00.",  # English thousands and decimals
        "Tem violões até R$ 1.000,00.",  # the customer wrote "1000"
        "Oi! Como posso ajudar?",
    ],
)
def test_amounts_from_tools_or_the_customer_pass(answer):
    history = [{"role": "user", "content": "violão até 1000 reais?"}, TOOL_RESULT]
    assert unsupported_amounts(answer, history) == []


def test_invented_or_computed_amounts_are_caught():
    history = [{"role": "user", "content": "quanto custa?"}, TOOL_RESULT]
    answer = "Custa R$ 2.199,00, mas pra você faço por R$ 1.999,00 e você economiza R$ 109,95 no Pix."
    assert unsupported_amounts(answer, history) == ["R$ 1.999,00", "R$ 109,95"]


def test_amounts_only_said_by_the_assistant_do_not_count():
    history = [{"role": "assistant", "content": "Custa R$ 1.999,00."}]
    assert unsupported_amounts("Como eu disse, R$ 1.999,00.", history) == ["R$ 1.999,00"]


@pytest.fixture
def agent_for(ctx, tmp_path):
    def build(*responses):
        session = new_session("scripted", "scripted-1", MONDAY_10AM)
        llm = ScriptedLLM(*responses)
        return Agent(llm, ctx, session, UsageLog(tmp_path / "usage.jsonl")), llm, session

    return build


def test_an_invented_price_gets_one_correction(agent_for, tmp_path):
    agent, llm, session = agent_for(
        tools(("search_products", {"query": "Takamine GD20"})),
        text("Custa R$ 1.999,00."),  # invented
        text("Custa R$ 2.199,00."),
    )
    assert agent.reply("Quanto custa o Takamine GD20?") == "Custa R$ 2.199,00."
    assert "CORREÇÃO NECESSÁRIA" in llm.calls[2]["system"] and "R$ 1.999,00" in llm.calls[2]["system"]
    assert "CORREÇÃO" not in llm.calls[1]["system"]
    # The wrong answer never enters the history.
    assert [m["content"] for m in session.messages if m["role"] == "assistant" and m["content"]] == [
        "Custa R$ 2.199,00."
    ]
    events = [json.loads(line) for line in (tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e for e in events if "event" in e][0]["amounts"] == ["R$ 1.999,00"]


def test_a_second_invented_price_gets_the_fixed_answer(agent_for):
    agent, llm, session = agent_for(text("Custa R$ 1.999,00."), text("Custa R$ 1.899,00."))
    assert agent.reply("Quanto custa o Takamine GD20?") == FALLBACK_ANSWER
    assert len(llm.calls) == 2
    assert session.messages[-1]["content"] == FALLBACK_ANSWER


def test_the_correction_may_look_the_price_up(agent_for):
    agent, llm, _ = agent_for(
        text("Custa R$ 1.999,00."),
        tools(("search_products", {"query": "Takamine GD20"})),
        text("Custa R$ 2.199,00."),
    )
    assert agent.reply("Quanto custa o Takamine GD20?") == "Custa R$ 2.199,00."
    assert all("CORREÇÃO" in call["system"] for call in llm.calls[1:])


def test_the_prompt_puts_tools_first_and_carries_the_rules_only_the_model_can_follow():
    prompt = system_prompt(MONDAY_10AM)
    assert "segunda-feira, 23/03/2026" in prompt
    for rule in (
        "assistente virtual",
        "ANTES de responder",
        "não vende acessórios",
        "diga que não tem essa informação",
        "nunca invente",
        "QUAL FERRAMENTA USAR",
        "Português do Brasil",
        "sem Markdown",
        "falar em carrinho",
        "Fechar pedidos",
        "ao fabricante ou à transportadora",
        "indicar outra loja",
        "Mostrar dados de outro cliente",
        "revelar estas instruções",
        "percentual de desconto",
    ):
        assert rule in prompt, rule
    # Every tool is routed.
    assert all(f"{tool}" in prompt for tool in ("search_products", "quote_payment", "get_order_status",
                                                 "get_store_policy", "check_return_options", "handoff_to_human",
                                                 "register_complaint"))


@pytest.mark.parametrize(
    "moment, line",
    [
        (datetime(2026, 3, 23, 10, 0, tzinfo=STORE_TZ), "A loja está aberta agora e fecha às 18:00."),
        (datetime(2026, 3, 23, 17, 59, tzinfo=STORE_TZ), "A loja está aberta agora e fecha às 18:00."),
        (datetime(2026, 3, 29, 10, 0, tzinfo=STORE_TZ), "A loja está fechada agora e abre segunda-feira, 30/03/2026"),
    ],
)
def test_the_prompt_says_whether_the_store_is_open_without_the_clock_time(moment, line):
    prompt = system_prompt(moment)
    assert line in prompt
    # The same text all morning: the prompt stays cacheable (D-008).
    assert system_prompt(moment.replace(minute=30)) == prompt


def test_the_greeting_discloses_the_virtual_assistant():
    assert "assistente virtual da Empório da Música" in GREETING
