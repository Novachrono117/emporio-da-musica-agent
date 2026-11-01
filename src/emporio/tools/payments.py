"""quote_payment: what a cart costs with each payment method (sections 3, 3.1, 5.1 and 6.2; D-005, rule 2; D-006).

The tool takes products and quantities, never a free amount, so every quote starts from catalog prices. Installments
have no interest; each one is the total divided by the count, rounded down to the cent, and the last one absorbs the
remaining cents so they add up to the total exactly.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from emporio.data.models import Availability
from emporio.tools.base import CENT, Result, Tool, ToolContext, ToolError, brl, current_price, percent_off

PIX_DISCOUNT_PERCENT = 5  # section 3, never over a promotional price (6.2)
MAX_INSTALLMENTS = 12
# Section 3.1 wins over the table in section 3: (from, to, minimum installment). A single payment has no minimum.
INSTALLMENT_TIERS = ((1, 3, Decimal("50")), (4, 6, Decimal("80")), (7, 12, Decimal("100")))
COMBINED_PAYMENT_ABOVE = Decimal("2000")  # 3.1
# 5.1: free above R$ 500 and R$ 35 below; exactly R$ 500 is in neither, so it ships free (the reading that favours
# the customer). The threshold applies to the cash price, before any Pix discount.
FREE_SHIPPING_FROM = Decimal("500")
METRO_SHIPPING_FEE = Decimal("35")

FOR_SALE = (Availability.AVAILABLE, Availability.LAST_UNITS)


def quote_payment(ctx: ToolContext, items: list[dict], method: str, installments: int | None = None) -> Result:
    if not items:
        raise ToolError("invalid_input", "items must list at least one product")
    quantities: dict[int, int] = {}
    for item in items:
        if item["quantity"] < 1:
            raise ToolError("invalid_input", "quantity must be at least 1")
        quantities[item["product_id"]] = quantities.get(item["product_id"], 0) + item["quantity"]
    if installments is not None and not 1 <= installments <= MAX_INSTALLMENTS:
        raise ToolError("invalid_input", f"installments must be between 1 and {MAX_INSTALLMENTS}")

    lines, cash_price, promotional = [], Decimal("0"), Decimal("0")
    for product_id, quantity in quantities.items():
        product = ctx.store.get_product(product_id)
        if product is None:
            raise ToolError("not_found", f"no product with id {product_id}")
        if product.availability not in FOR_SALE:
            raise ToolError("not_for_sale", f"{product.name} is not for sale ({product.availability.value})")
        if quantity > product.stock:
            raise ToolError("insufficient_stock", f"only {product.stock} unit(s) of {product.name} in stock")
        price, promotion = current_price(ctx.store, product)
        subtotal = price * quantity
        line: Result = {"product_id": product.id, "name": product.name, "quantity": quantity, "unit_price": brl(price)}
        if promotion is not None:
            line["list_price"] = brl(product.price)
            line["promotion"] = {"name": promotion.description, "discount_percent": promotion.discount_percent}
            promotional += subtotal
        line["subtotal"] = brl(subtotal)
        lines.append(line)
        cash_price += subtotal

    pix_price = promotional + percent_off(cash_price - promotional, PIX_DISCOUNT_PERCENT)
    max_installments = _max_installments(cash_price)
    quote: Result = {
        "items": lines,
        "cash_price": brl(cash_price),
        "pix_price": brl(pix_price),
        "method": method,
    }
    if promotional:
        quote["pix_note"] = "No Pix discount on promotional prices (6.2); it applies to the other items only."

    if method == "credit":
        count = installments or max_installments
        quote["total"] = brl(cash_price)  # no interest
        quote["max_installments"] = max_installments
        if count > max_installments:
            quote["valid"] = False
            quote["reason"] = _minimum_reason(count)
            count = max_installments
        else:
            quote["valid"] = True
        quote["installments"] = _plan(cash_price, count)
    else:
        quote["total"] = brl(pix_price if method == "pix" else cash_price)
        quote["valid"] = not installments or installments == 1
        if not quote["valid"]:
            quote["reason"] = "Installments are available on credit card only (3)."
        quote["credit_card_option"] = _plan(cash_price, max_installments)

    quote["combined_payment_allowed"] = cash_price > COMBINED_PAYMENT_ABOVE
    if quote["combined_payment_allowed"]:
        quote["combined_payment_note"] = "Allowed above R$ 2.000,00 (3.1); a person arranges the split."
    quote["shipping"] = {
        "campo_grande_metro": "Grátis" if cash_price >= FREE_SHIPPING_FROM else brl(METRO_SHIPPING_FEE),
        "other_cities": "Depends on CEP, weight and size; this service cannot calculate it (5.2).",
    }
    return quote


def _tier(count: int) -> tuple[int, int, Decimal]:
    return next(tier for tier in INSTALLMENT_TIERS if tier[0] <= count <= tier[1])


def _installment(total: Decimal, count: int) -> Decimal:
    return (total / count).quantize(CENT, ROUND_DOWN)


def _max_installments(total: Decimal) -> int:
    # The minimum grows with the count while each installment shrinks, so the allowed counts run from 1 upwards.
    allowed = [n for n in range(2, MAX_INSTALLMENTS + 1) if _installment(total, n) >= _tier(n)[2]]
    return max(allowed, default=1)


def _minimum_reason(count: int) -> str:
    first, last, minimum = _tier(count)
    return f"From {first}x to {last}x each installment must be at least {brl(minimum)} (3.1)."


def _plan(total: Decimal, count: int) -> Result:
    if count == 1:
        return {"count": 1, "amount": brl(total), "text": f"1x de {brl(total)} no cartão"}
    amount = _installment(total, count)
    last = total - amount * (count - 1)
    plan: Result = {"count": count, "amount": brl(amount)}
    if last == amount:
        plan["text"] = f"{count}x de {brl(amount)} sem juros"
    else:
        plan["last_amount"] = brl(last)
        plan["text"] = f"{count}x sem juros: {count - 1}x de {brl(amount)} e a última de {brl(last)}"
    return plan


TOOLS = (
    Tool(
        name="quote_payment",
        description=(
            "Price a purchase: cash price, Pix price, total for the chosen method and credit card installments, "
            "with the store's discount and installment rules applied, plus delivery cost in Campo Grande. Use it "
            "for every question about how much something costs to pay or in how many installments. List each "
            "product and quantity; the tool adds them up."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "Products to buy, each with its quantity.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer", "description": "Product id from the catalog."},
                            "quantity": {"type": "integer", "description": "Units, at least 1."},
                        },
                        "required": ["product_id", "quantity"],
                        "additionalProperties": False,
                    },
                },
                "method": {
                    "type": "string",
                    "enum": ["pix", "debit", "credit", "boleto"],
                    "description": "Payment method.",
                },
                "installments": {
                    "type": "integer",
                    "description": "Credit card installments, 1 to 12. Leave out to get the maximum allowed.",
                },
            },
            "required": ["items", "method"],
            "additionalProperties": False,
        },
        handler=quote_payment,
    ),
)
