"""register_complaint and handoff_to_human: both record a ticket in the local log (decision D-006).

A hand-off also records regret requests and warranty claims, which a person must process (D-005, rules 4 and 5), and
tells the agent whether the store is open now and when it opens next (7.1).
"""

from __future__ import annotations

from emporio.company import CONTACTS, HOURS_TEXT, store_status
from emporio.tools.base import Result, Tool, ToolContext, ToolError

MAX_TEXT = 2000
HANDOFF_REASONS = (
    "customer_request",
    "regret_request",
    "warranty_claim",
    "policy_question",
    "order_verification_failed",
    "other",
)


def register_complaint(ctx: ToolContext, summary: str, contact: str | None = None) -> Result:
    fields = _fields(summary, contact)
    ticket_id = ctx.tickets.open("complaint", ctx.now(), **fields)
    return {
        "ticket_id": ticket_id,
        "response_time": "até 24 horas úteis",
        "message": "Tell the customer the complaint was recorded, with the ticket id, and that the person in charge "
        "replies within 24 business hours (7.3).",
    }


def handoff_to_human(ctx: ToolContext, reason: str, summary: str, contact: str | None = None) -> Result:
    fields = _fields(summary, contact)
    now = ctx.now()
    ticket_id = ctx.tickets.open("handoff", now, reason=reason, **fields)
    message = "Tell the customer a person will continue the service and give the ticket id."
    if reason == "regret_request":
        message = "Confirm to the customer that the regret request was received, with the ticket id."
    return {
        "ticket_id": ticket_id,
        "message": message,
        "contacts": CONTACTS,
        "hours": HOURS_TEXT,
        **store_status(now),
    }


def _fields(summary: str, contact: str | None) -> dict[str, str]:
    if not summary:
        raise ToolError("invalid_input", "summary must not be empty")
    if len(summary) > MAX_TEXT or (contact and len(contact) > MAX_TEXT):
        raise ToolError("invalid_input", f"summary and contact must have at most {MAX_TEXT} characters")
    return {"summary": summary, "contact": contact} if contact else {"summary": summary}


_CONTACT = {
    "type": "string",
    "description": "How the store can reach the customer, only if the customer offered it (phone or e-mail).",
}

TOOLS = (
    Tool(
        name="register_complaint",
        description=(
            "Record a customer complaint for the person in charge, who replies within 24 business hours. Listen "
            "first, then summarise the complaint in the customer's words."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What happened, in a few sentences."},
                "contact": _CONTACT,
            },
            "required": ["summary"],
            "additionalProperties": False,
        },
        handler=register_complaint,
    ),
    Tool(
        name="handoff_to_human",
        description=(
            "Pass the conversation to a person and record a ticket. Use it when the customer asks for a person, to "
            "record a regret request or a warranty claim, when a policy is unclear (the manual says to consult "
            "management), or after failed order verification. Returns contacts, hours and whether the store is open."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "reason": {"type": "string", "enum": list(HANDOFF_REASONS), "description": "Why a person is needed."},
                "summary": {"type": "string", "description": "What the customer needs, for the person who takes over."},
                "contact": _CONTACT,
            },
            "required": ["reason", "summary"],
            "additionalProperties": False,
        },
        handler=handoff_to_human,
    ),
)
