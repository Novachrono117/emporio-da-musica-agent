"""quote_payment: cart totals, Pix discount, installment tiers and exact installments (D-005, rule 2; D-006)."""

from decimal import Decimal

import pytest

from emporio.tools.base import ToolError
from emporio.tools.payments import _max_installments, _plan, quote_payment


def _money(text):
    return Decimal(text.removeprefix("R$ ").replace(".", "").replace(",", "."))


def _items(*pairs):
    return [{"product_id": product_id, "quantity": quantity} for product_id, quantity in pairs]


def test_cart_is_added_up_in_code_with_promotions_applied(ctx):
    # 81 at R$ 599,90 plus 127 at R$ 359,00 with 10% off (R$ 323,10).
    quote = quote_payment(ctx, _items((81, 1), (127, 1)), "credit", 6)
    assert quote["cash_price"] == quote["total"] == "R$ 923,00"
    assert quote["items"][1]["list_price"] == "R$ 359,00"
    assert quote["items"][1]["promotion"] == {"name": "Oferta Especial", "discount_percent": 10}


def test_pix_discount_skips_promotional_prices(ctx):
    # 5% off 599,90 is 569,905, rounded to 569,91; the promotional 323,10 stays as it is.
    assert quote_payment(ctx, _items((81, 1), (127, 1)), "pix")["pix_price"] == "R$ 893,01"
    assert quote_payment(ctx, _items((95, 1)), "pix")["total"] == "R$ 2.089,05"
    promotional = quote_payment(ctx, _items((94, 1)), "pix")
    assert promotional["total"] == promotional["cash_price"] == "R$ 5.519,08"
    assert "6.2" in promotional["pix_note"]


def test_every_quote_shows_cash_pix_and_installments(ctx):
    quote = quote_payment(ctx, _items((95, 1)), "boleto")
    assert (quote["cash_price"], quote["pix_price"], quote["total"]) == ("R$ 2.199,00", "R$ 2.089,05", "R$ 2.199,00")
    assert quote["credit_card_option"]["text"] == "12x de R$ 183,25 sem juros"


def test_installments_add_up_to_the_total_exactly():
    for total in (Decimal("923.00"), Decimal("359.00"), Decimal("5519.08"), Decimal("19567.00"), Decimal("1000.01")):
        for count in range(2, 13):
            plan = _plan(total, count)
            last = _money(plan.get("last_amount", plan["amount"]))
            assert _money(plan["amount"]) * (count - 1) + last == total
            assert Decimal("0") <= last - _money(plan["amount"]) < Decimal("0.01") * count


def test_uneven_installments_say_so(ctx):
    plan = quote_payment(ctx, _items((81, 1), (127, 1)), "credit", 6)["installments"]
    assert plan == {
        "count": 6,
        "amount": "R$ 153,83",
        "last_amount": "R$ 153,85",
        "text": "6x sem juros: 5x de R$ 153,83 e a última de R$ 153,85",
    }


@pytest.mark.parametrize(
    "total, expected",
    [
        ("429.90", 5),  # 6x would be R$ 71,65, below the R$ 80 minimum from 4x to 6x
        ("323.10", 4),  # 4x is R$ 80,77; 5x would be R$ 64,62
        ("159.90", 3),  # 3x is R$ 53,30, above R$ 50
        ("1200.00", 12),  # exactly R$ 100 per installment is allowed
        ("1199.99", 11),
        ("99.00", 1),  # 2x would be below R$ 50
    ],
)
def test_installment_tiers_from_section_3_1(total, expected):
    assert _max_installments(Decimal(total)) == expected


def test_too_many_installments_are_refused_with_the_rule(ctx):
    quote = quote_payment(ctx, _items((83, 1)), "credit", 6)
    assert quote["valid"] is False
    assert quote["reason"] == "From 4x to 6x each installment must be at least R$ 80,00 (3.1)."
    assert (quote["max_installments"], quote["installments"]["text"]) == (5, "5x de R$ 85,98 sem juros")


def test_credit_without_a_count_offers_the_maximum(ctx):
    quote = quote_payment(ctx, _items((83, 1)), "credit")
    assert (quote["valid"], quote["installments"]["count"]) == (True, 5)
    assert quote_payment(ctx, _items((83, 1)), "credit", 1)["installments"]["text"] == "1x de R$ 429,90 no cartão"


def test_installments_only_on_credit_card(ctx):
    quote = quote_payment(ctx, _items((95, 1)), "debit", 3)
    assert quote["valid"] is False
    assert "credit card only" in quote["reason"]


def test_combined_payment_uses_the_price_after_promotion(ctx):
    # 90 lists at R$ 2.399,00 but costs R$ 1.967,18 with 18% off: not above R$ 2.000.
    assert quote_payment(ctx, _items((90, 1)), "credit")["combined_payment_allowed"] is False
    assert quote_payment(ctx, _items((95, 1)), "credit")["combined_payment_allowed"] is True


def test_metro_shipping_is_free_from_500(ctx):
    assert quote_payment(ctx, _items((83, 1)), "pix")["shipping"]["campo_grande_metro"] == "R$ 35,00"
    assert quote_payment(ctx, _items((81, 1)), "pix")["shipping"]["campo_grande_metro"] == "Grátis"
    assert "cannot calculate" in quote_payment(ctx, _items((81, 1)), "pix")["shipping"]["other_cities"]


def test_repeated_products_are_merged(ctx):
    quote = quote_payment(ctx, _items((81, 1), (81, 2)), "pix")
    assert [(item["product_id"], item["quantity"], item["subtotal"]) for item in quote["items"]] == [
        (81, 3, "R$ 1.799,70")
    ]


@pytest.mark.parametrize(
    "items, code",
    [
        (_items((130, 1)), "not_for_sale"),  # coming soon
        (_items((96, 1)), "not_for_sale"),  # out of stock
        (_items((113, 1)), "not_for_sale"),  # discontinued, no stock
        (_items((93, 3)), "insufficient_stock"),  # 2 in stock
        (_items((1, 1)), "not_found"),
        ([], "invalid_input"),
        (_items((81, 0)), "invalid_input"),
    ],
)
def test_quotes_only_for_products_on_sale(ctx, items, code):
    with pytest.raises(ToolError) as error:
        quote_payment(ctx, items, "pix")
    assert error.value.code == code


def test_installment_count_must_be_1_to_12(ctx):
    with pytest.raises(ToolError, match="between 1 and 12"):
        quote_payment(ctx, _items((95, 1)), "credit", 13)
