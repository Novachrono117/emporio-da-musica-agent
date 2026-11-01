"""check_return_options: deadlines for regret, defect and preference exchange, computed in code (decision D-006).

Days are counted excluding the first day and including the last (Código Civil, art. 132): a product received on the
16th can be returned until the 23rd. The tool says whether a request is within the deadline, never that it is
eligible: the product's condition is checked by a person, and what the agent tells a customer binds the store (CDC,
art. 30). A defect is never denied (D-005, rule 4).
"""

from __future__ import annotations

from datetime import date, timedelta

from emporio.tools.base import Result, Tool, ToolContext, ToolError, br_date, parse_date

REGRET_DAYS = 7  # 4.1 and CDC art. 49, from receipt
DEFECT_EXCHANGE_DAYS = 30  # 4.2, from the purchase
PREFERENCE_DAYS = 7  # 4.3, from receipt, which is the purchase day in the store (D-006)
LEGAL_WARRANTY_DAYS = 90  # 8.1 and CDC art. 26, from receipt

ASK_DATES = "Ask the customer for the missing information; do not guess dates or how the purchase was made."
NOT_COVERED = (
    "Damage from misuse, falls, excessive humidity or extreme weather (4.2, 8.3).",
    "Unauthorised modifications or repairs (4.2, 8.3).",
    "Natural wear of parts such as frets, strings and felts (8.3).",
)


def check_return_options(
    ctx: ToolContext,
    reason: str,
    channel: str | None = None,
    purchase_date: str | None = None,
    received_date: str | None = None,
) -> Result:
    today = ctx.today()
    purchased = parse_date(purchase_date, "purchase_date") if purchase_date else None
    received = parse_date(received_date, "received_date") if received_date else None
    for day in (purchased, received):
        if day and day > today:
            raise ToolError("invalid_input", f"dates cannot be in the future; today is {br_date(today)}")
    if purchased and received and received < purchased:
        raise ToolError("invalid_input", "received_date cannot be before purchase_date")
    if channel == "in_store" and purchased and not received:
        received = purchased  # taken home on the day of the purchase

    result: Result = {"today": br_date(today), "reason": reason}
    if reason == "regret":
        return result | _regret(channel, received, today)
    if reason == "defect":
        return result | _defect(purchased, received, today)
    return result | _preference(received, today)


def _window(start: date, days: int, today: date) -> Result:
    deadline = start + timedelta(days=days)
    return {
        "within_deadline": today <= deadline,
        "deadline": br_date(deadline),
        "days_left": max((deadline - today).days, 0),
    }


def _regret(channel: str | None, received: date | None, today: date) -> Result:
    if channel == "in_store":
        return {
            "policy": "4.1",
            "applies": False,
            "explanation": "The regret right covers purchases made outside the store only (4.1; CDC, art. 49).",
            "alternative": "Preference exchange within 7 days (4.3): call again with reason preference.",
        }
    missing = [name for name, value in (("channel", channel), ("received_date", received)) if value is None]
    if missing:
        return {"missing": missing, "message": ASK_DATES}
    window = _window(received, REGRET_DAYS, today)
    return {
        "policy": "4.1",
        "applies": True,
        **window,
        "conditions_checked_by_a_person": [
            "Original packaging, no signs of use, with all accessories and manuals (4.1).",
        ],
        "refund": "Same payment method, within 10 business days; the store pays the return shipping (4.1).",
        "next_step": (
            "Record the request with handoff_to_human, reason regret_request, and confirm to the customer that it "
            "was received, with the ticket id."
            if window["within_deadline"]
            else f"Explain that the 7 days ended on {window['deadline']}. If the customer disagrees, offer a person "
            "(handoff_to_human)."
        ),
    }


def _defect(purchased: date | None, received: date | None, today: date) -> Result:
    if purchased is None and received is None:
        return {"missing": ["purchase_date", "received_date"], "message": ASK_DATES}
    options = []
    if purchased:
        exchange = _window(purchased, DEFECT_EXCHANGE_DAYS, today)
        options.append({"policy": "4.2", "option": "exchange at the store", **exchange})
    if received:
        warranty: Result = {
            "policy": "8.1",
            "option": "legal warranty",
            **_window(received, LEGAL_WARRANTY_DAYS, today),
        }
        if not warranty["within_deadline"]:
            warranty["note"] = (
                "For a hidden defect the 90 days count from when it shows up (CDC, art. 26, paragraph 3), and the "
                "manufacturer's warranty may still apply (8.2): a person must assess it."
            )
        options.append(warranty)
    in_store_exchange = bool(options[0]["within_deadline"]) if purchased else False
    result: Result = {
        "options": options,
        "not_covered": list(NOT_COVERED),
        "rules": [
            "Never deny the claim and never send the customer to the manufacturer: the store and the manufacturer "
            "answer jointly (CDC, art. 18); the store can handle the manufacturer's warranty (4.2).",
        ],
        "next_step": (
            "Explain the exchange at the store (4.2) and hand off with reason warranty_claim so a person arranges it."
            if in_store_exchange
            else "Explain the legal warranty and hand off with reason warranty_claim; a person assesses the defect."
        ),
    }
    if not received:
        result["missing"] = ["received_date"]
        result["message"] = "Ask when the product was received to check the 90-day legal warranty (8.1)."
    return result


def _preference(received: date | None, today: date) -> Result:
    if received is None:
        return {"missing": ["received_date"], "message": ASK_DATES}
    window = _window(received, PREFERENCE_DAYS, today)
    return {
        "policy": "4.3",
        **window,
        "conditions_checked_by_a_person": [
            "Perfect condition, in the original packaging (4.3).",
            "The product wanted must be available; price differences are charged or refunded (4.3).",
        ],
        "not_eligible": [
            "Instruments with custom setup or adjustments made to order (4.4).",
            "Clearance sales marked as final sale ('venda final') (4.4).",
        ],
        "next_step": (
            "Hand off with reason customer_request so a person arranges the exchange."
            if window["within_deadline"]
            else f"Explain that the 7 days ended on {window['deadline']}."
        ),
    }


TOOLS = (
    Tool(
        name="check_return_options",
        description=(
            "Deadlines and conditions for returning or exchanging a product: regret (purchase made online or by "
            "phone), a defect, or an exchange for another model, color or size. Ask the customer how and when they "
            "bought and received the product before calling; never compute these deadlines yourself."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "enum": ["regret", "defect", "preference"],
                    "description": "regret: gave up the purchase; defect: the product has a problem; preference: "
                    "wants another model, color or size.",
                },
                "channel": {
                    "type": "string",
                    "enum": ["online", "phone", "in_store"],
                    "description": "How the purchase was made.",
                },
                "purchase_date": {"type": "string", "description": "Date of the purchase, YYYY-MM-DD."},
                "received_date": {"type": "string", "description": "Date the product was received, YYYY-MM-DD."},
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
        handler=check_return_options,
    ),
)
