"""register_complaint and handoff_to_human record tickets and report contacts and hours (D-005; D-006)."""

from datetime import datetime

import pytest

from emporio.config import STORE_TZ
from emporio.tools.base import ToolError
from emporio.tools.support import handoff_to_human, register_complaint


def test_complaint_is_recorded_with_the_24_hour_promise(ctx):
    result = register_complaint(ctx, "O violão chegou riscado.", contact="ana@example.com")
    assert result["ticket_id"] == "EMP-20260323-0001"
    assert result["response_time"] == "até 24 horas úteis"
    [ticket] = ctx.tickets.read()
    assert ticket == {
        "id": "EMP-20260323-0001",
        "kind": "complaint",
        "created_at": "2026-03-23T10:00:00-04:00",
        "summary": "O violão chegou riscado.",
        "contact": "ana@example.com",
    }


def test_regret_request_is_recorded_and_confirmed(ctx):
    register_complaint(ctx, "first ticket")
    result = handoff_to_human(ctx, "regret_request", "Quer devolver o pedido 5, recebido em 20/03.")
    assert result["ticket_id"] == "EMP-20260323-0002"
    assert "regret request was received" in result["message"]
    assert ctx.tickets.read()[-1]["reason"] == "regret_request"
    assert "contact" not in ctx.tickets.read()[-1]


def test_handoff_gives_contacts_and_hours_while_open(ctx):
    result = handoff_to_human(ctx, "customer_request", "Quer falar com um vendedor.")
    assert result["contacts"]["whatsapp"] == "(67) 3321-4500"
    assert (result["open_now"], result["closes_at"]) == (True, "18:00")


def test_handoff_outside_hours_says_when_the_store_opens(ctx):
    ctx.now = lambda: datetime(2026, 3, 28, 15, 0, tzinfo=STORE_TZ)  # Saturday afternoon
    result = handoff_to_human(ctx, "warranty_claim", "Defeito no captador depois de 40 dias.")
    assert result["open_now"] is False
    assert result["next_opening"] == "segunda-feira, 30/03/2026, às 09:00"


@pytest.mark.parametrize("summary", ["", "x" * 2001])
def test_summary_must_be_present_and_short(ctx, summary):
    with pytest.raises(ToolError):
        register_complaint(ctx, summary)
    assert ctx.tickets.read() == []
