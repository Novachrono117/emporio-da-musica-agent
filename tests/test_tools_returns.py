"""check_return_options: deadlines computed in code, never "eligible", never a denied defect (D-005, rules 4 and 5)."""

import pytest

from emporio.tools.base import ToolError
from emporio.tools.returns import check_return_options

# Today is 23/03/2026 (conftest).


def test_regret_counts_7_days_from_receipt_excluding_the_first_day(ctx):
    result = check_return_options(ctx, "regret", channel="online", received_date="2026-03-16")
    assert (result["applies"], result["within_deadline"], result["deadline"], result["days_left"]) == (
        True, True, "23/03/2026", 0
    )
    assert "regret_request" in result["next_step"]
    assert "eligible" not in result


def test_regret_after_the_deadline(ctx):
    result = check_return_options(ctx, "regret", channel="phone", received_date="2026-03-15")
    assert (result["within_deadline"], result["deadline"]) == (False, "22/03/2026")
    assert "ended on 22/03/2026" in result["next_step"]


def test_regret_lists_the_conditions_a_person_checks_and_the_refund_policy(ctx):
    result = check_return_options(ctx, "regret", channel="online", received_date="2026-03-20")
    assert result["days_left"] == 4
    assert "Original packaging" in result["conditions_checked_by_a_person"][0]
    assert "10 business days" in result["refund"]


def test_regret_does_not_apply_to_in_store_purchases(ctx):
    result = check_return_options(ctx, "regret", channel="in_store", purchase_date="2026-03-20")
    assert result["applies"] is False
    assert "outside the store" in result["explanation"]
    assert "4.3" in result["alternative"]


def test_regret_asks_instead_of_guessing(ctx):
    result = check_return_options(ctx, "regret")
    assert result["missing"] == ["channel", "received_date"]
    assert "do not guess" in result["message"]


def test_defect_within_30_days_is_an_exchange_at_the_store(ctx):
    result = check_return_options(ctx, "defect", purchase_date="2026-03-01", received_date="2026-03-03")
    exchange, warranty = result["options"]
    assert (exchange["policy"], exchange["within_deadline"], exchange["deadline"]) == ("4.2", True, "31/03/2026")
    assert (warranty["policy"], warranty["deadline"]) == ("8.1", "01/06/2026")
    assert "exchange at the store" in result["next_step"]


def test_defect_after_30_days_is_never_denied(ctx):
    result = check_return_options(ctx, "defect", purchase_date="2026-01-10", received_date="2026-01-12")
    exchange, warranty = result["options"]
    assert exchange["within_deadline"] is False
    assert (warranty["within_deadline"], warranty["deadline"]) == (True, "12/04/2026")
    assert "warranty_claim" in result["next_step"]
    assert "never send the customer to the manufacturer" in result["rules"][0]


def test_defect_after_90_days_still_goes_to_a_person(ctx):
    result = check_return_options(ctx, "defect", purchase_date="2025-10-15", received_date="2025-10-25")
    warranty = result["options"][1]
    assert warranty["within_deadline"] is False
    assert "hidden defect" in warranty["note"]
    assert "warranty_claim" in result["next_step"]


def test_defect_without_receipt_date_asks_for_it(ctx):
    result = check_return_options(ctx, "defect", purchase_date="2026-03-01")
    assert result["missing"] == ["received_date"]
    in_store = check_return_options(ctx, "defect", channel="in_store", purchase_date="2026-03-01")
    assert "missing" not in in_store  # taken home on the purchase day
    assert in_store["options"][1]["deadline"] == "30/05/2026"


def test_preference_exchange_lists_what_is_not_eligible(ctx):
    result = check_return_options(ctx, "preference", channel="in_store", purchase_date="2026-03-17")
    assert (result["policy"], result["within_deadline"], result["deadline"]) == ("4.3", True, "24/03/2026")
    assert any("venda final" in item for item in result["not_eligible"])
    online = check_return_options(ctx, "preference", channel="online", purchase_date="2026-03-17")
    assert online["missing"] == ["received_date"]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"received_date": "2026-03-24"}, "cannot be in the future"),
        ({"purchase_date": "2026-03-10", "received_date": "2026-03-09"}, "cannot be before"),
        ({"received_date": "16/03/2026"}, "YYYY-MM-DD"),
    ],
)
def test_bad_dates_are_rejected(ctx, kwargs, message):
    with pytest.raises(ToolError, match=message):
        check_return_options(ctx, "regret", channel="online", **kwargs)
