"""get_order_status: an order is shown only when its number and the last 4 digits of the customer's phone match.

The check runs here, so the model never sees a phone number, and every failure gets the same message whatever failed.
After 3 failures in a session the tool stops checking (D-005, rule 11; D-006). The result carries only what the
customer needs: no name, phone or e-mail, and no item prices, so the model cannot recompute a recorded total (rule 8).
"""

from __future__ import annotations

import hmac
import re

from emporio.data.models import Order, OrderStatus, PaymentMethod
from emporio.tools.base import Result, Tool, ToolContext, ToolError, br_date, brl

MAX_FAILED_LOOKUPS = 3
NOT_VERIFIED = "The order number and phone ending do not match an order. Ask the customer to check both."
LOCKED = (
    "Too many failed verifications in this conversation: do not check again. Hand off to a person with "
    "handoff_to_human, reason order_verification_failed."
)
OPEN_STATUSES = (OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.SHIPPED)
LATE_DELIVERY_NOTE = (
    "The estimated delivery date has passed. Apologise and offer a person from the team (handoff_to_human, reason "
    "customer_request); do not send the customer to the carrier."
)


def get_order_status(ctx: ToolContext, order_id: int, phone_last4: str) -> Result:
    if ctx.failed_order_lookups >= MAX_FAILED_LOOKUPS:
        return {"verified": False, "locked": True, "message": LOCKED}
    if not re.fullmatch(r"\d{4}", phone_last4):
        raise ToolError("invalid_input", "phone_last4 must be exactly 4 digits")

    order = ctx.store.get_order(order_id)
    customer = ctx.store.get_customer(order.customer_id) if order else None
    if order is None or customer is None or not hmac.compare_digest(customer.phone_last4, phone_last4):
        if ctx.last_failed_lookup == (order_id, phone_last4):
            # The model repeating the same call is not a new attempt by the customer (seen with Gemini Flash-Lite).
            return {"verified": False, "attempts_left": MAX_FAILED_LOOKUPS - ctx.failed_order_lookups,
                    "message": NOT_VERIFIED}
        ctx.last_failed_lookup = (order_id, phone_last4)
        ctx.failed_order_lookups += 1
        attempts_left = MAX_FAILED_LOOKUPS - ctx.failed_order_lookups
        if attempts_left == 0:
            return {"verified": False, "locked": True, "message": LOCKED}
        return {"verified": False, "attempts_left": attempts_left, "message": NOT_VERIFIED}
    return {"verified": True, "order": _order(ctx, order)}


def _order(ctx: ToolContext, order: Order) -> Result:
    items = []
    for item in order.items:
        product = ctx.store.get_product(item.product_id)
        items.append({"product": product.name if product else f"product {item.product_id}", "quantity": item.quantity})
    result: Result = {
        "order_id": order.id,
        "status": order.status.value,
        "order_date": br_date(order.order_date),
        "items": items,
        "total": brl(order.total),  # as recorded (D-005, rule 8)
        "payment_method": order.payment_method.value,
    }
    if order.payment_method is PaymentMethod.CREDIT:
        result["installments"] = order.installments  # as recorded (D-005, rule 9)
    if order.tracking_code:
        result["tracking_code"] = order.tracking_code
        result["tracking_note"] = "Track it on the Correios or Jadlog website (5.3)."
    if order.estimated_delivery:
        result["estimated_delivery"] = br_date(order.estimated_delivery)
        if order.status in OPEN_STATUSES and order.estimated_delivery < ctx.today():
            result["estimated_delivery_passed"] = True
            result["delivery_note"] = LATE_DELIVERY_NOTE
    if order.notes:
        result["notes"] = order.notes
    return result


TOOLS = (
    Tool(
        name="get_order_status",
        description=(
            "Status of a customer's order: items, recorded total, payment, tracking code and estimated delivery. "
            "Needs the order number AND the last 4 digits of the phone number registered with the order; ask the "
            "customer for both. Never guess them or reuse digits the customer did not give."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "integer", "description": "Order number, e.g. 8."},
                "phone_last4": {"type": "string", "description": "Last 4 digits of the customer's phone, e.g. '7821'."},
            },
            "required": ["order_id", "phone_last4"],
            "additionalProperties": False,
        },
        handler=get_order_status,
    ),
)
