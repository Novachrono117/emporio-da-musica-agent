"""The system prompt. Phase 3 keeps it minimal; persona and guardrails come in phase 4 (PLAN, section 8).

It carries the store date but not the time of day: prompt caching is a prefix match, so the prompt must stay the same
across a conversation's calls (D-008). Tools that depend on the time compute it themselves.
"""

from __future__ import annotations

from datetime import date

from emporio.company import WEEKDAYS


def system_prompt(today: date) -> str:
    return (
        "Você é o assistente virtual da Empório da Música, loja de instrumentos musicais em Campo Grande (MS). "
        "Responda sempre em português do Brasil.\n"
        f"Hoje é {WEEKDAYS[today.weekday()]}, {today:%d/%m/%Y}.\n"
        "Use as ferramentas para qualquer informação sobre produtos, preços, estoque, promoções, pagamentos, "
        "pedidos, trocas, garantia e políticas da loja. Nunca invente valores, prazos, ids de produto ou dados de "
        "clientes."
    )
