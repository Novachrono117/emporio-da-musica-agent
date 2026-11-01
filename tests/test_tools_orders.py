"""get_order_status: verification in code, neutral failures, lockout and minimal data (D-005, rules 8, 9 and 11)."""

import json

import pytest

from emporio.tools.base import ToolError
from emporio.tools.orders import get_order_status


def test_verified_order_shows_status_tracking_and_late_delivery(ctx):
    result = get_order_status(ctx, 8, "7821")  # customer 2, (67) 99654-7821
    assert result["verified"] is True
    order = result["order"]
    assert (order["status"], order["order_date"], order["total"]) == ("shipped", "15/02/2026", "R$ 349,90")
    assert order["items"] == [{"product": "Kala KA-C Concert Mogno", "quantity": 1}]
    assert order["tracking_code"] == "BRJL5544332BR"
    assert order["estimated_delivery"] == "28/02/2026"
    assert order["estimated_delivery_passed"] is True  # today is 23/03/2026


def test_result_carries_no_personal_data(ctx, store):
    order = get_order_status(ctx, 8, "7821")["order"]
    customer = store.get_customer(store.get_order(8).customer_id)
    text = json.dumps(order, ensure_ascii=False)
    for value in (customer.name, customer.phone, customer.email, "7821"):
        assert value not in text


def test_totals_and_installments_are_shown_as_recorded(ctx):
    order = get_order_status(ctx, 3, "9012")["order"]  # customer 12, (67) 99678-9012
    assert order["total"] == "R$ 3.450,00"  # not 2 x R$ 1.749,00 (D-005, rule 8)
    assert (order["payment_method"], order["installments"]) == ("credit", 12)
    assert "estimated_delivery_passed" not in order  # delivered
    assert "unit_price" not in json.dumps(order)


def test_cancelled_order_shows_its_note(ctx):
    order = get_order_status(ctx, 17, "8765")["order"]  # customer 15, (67) 98109-8765
    assert order["status"] == "cancelled"
    assert order["notes"] == "Pedido cancelado pelo cliente antes do processamento"
    assert "tracking_code" not in order and "installments" not in order


def test_wrong_phone_and_unknown_order_look_the_same(ctx):
    wrong_phone = get_order_status(ctx, 8, "0000")
    unknown_order = get_order_status(ctx, 999, "7821")
    assert wrong_phone["message"] == unknown_order["message"]
    assert (wrong_phone["verified"], wrong_phone["attempts_left"]) == (False, 2)
    assert unknown_order["attempts_left"] == 1
    assert "order" not in wrong_phone


def test_three_failures_lock_the_lookup_for_the_session(ctx):
    for _ in range(2):
        get_order_status(ctx, 8, "0000")
    third = get_order_status(ctx, 8, "1111")
    assert third["locked"] is True and "handoff_to_human" in third["message"]
    # Even the right pair is refused now: the agent must hand off.
    assert get_order_status(ctx, 8, "7821") == third


def test_malformed_phone_ending_is_an_input_error_not_an_attempt(ctx):
    for bad in ("78", "78a1", "(67) 99654-7821"):
        with pytest.raises(ToolError, match="exactly 4 digits"):
            get_order_status(ctx, 8, bad)
    assert ctx.failed_order_lookups == 0
