"""get_store_policy: the manual's sections for a topic, with notes where the business rules resolve a conflict.

Notes cite only the manual and the law, which the agent may quote to a customer (decision D-006, choice 6). Contact
data comes from emporio.company, not from the manual's text, because the manual gives conflicting e-mails and
WhatsApp numbers (D-005, rule 3).
"""

from __future__ import annotations

from emporio.company import COMPANY, CONTACTS, HOURS_TEXT, store_status
from emporio.tools.base import Result, Tool, ToolContext, ToolError

TOPICS: dict[str, tuple[str, ...]] = {
    "about": ("1", "1.1"),
    "hours": ("2",),
    "payment": ("3", "3.1"),
    "returns_exchanges": ("4", "4.1", "4.2", "4.3", "4.4"),
    "shipping": ("5.1", "5.2", "5.3"),
    "promotions": ("6.1", "6.2"),
    "warranty": ("4.2", "8.1", "8.2", "8.3"),
    "privacy": ("9",),
    "contact": (),
}

_DEFECT_NOTE = (
    "For a defect after 30 days, never deny the claim and never send the customer to the manufacturer: the store and "
    "the manufacturer answer jointly (CDC, art. 18). Explain the legal warranty and hand off to a person "
    "(handoff_to_human, reason warranty_claim); check_return_options gives the dates."
)

NOTES: dict[str, tuple[str, ...]] = {
    "about": (
        "Instruments only: redirect requests for strings, picks, cables, cases, pedals or amplifiers politely, "
        "without naming another store (7.1).",
        "Which instruments are available comes from search_products, never from this description of the catalog; "
        "do not promise restocking.",
    ),
    "hours": ("Outside business hours, tell the customer when the store opens again (7.1).",),
    "payment": (
        "Section 3.1 overrides the credit card line of the table in section 3: each installment is at least "
        "R$ 50,00 up to 3x, R$ 80,00 from 4x to 6x and R$ 100,00 from 7x to 12x, with no interest.",
        "Use quote_payment for any amount: it applies these rules and the Pix discount, which never applies to "
        "promotional prices (6.2).",
    ),
    "returns_exchanges": (
        "Regret (4.1) applies only to purchases made outside the store (online or by phone), within 7 calendar days "
        "of receipt (CDC, art. 49). Ask how and when the product was received; do not infer it.",
        "In-store purchases have no regret right, but have the preference exchange within 7 days (4.3).",
        "Use check_return_options for any deadline; never count the days yourself.",
        "Refund: state the store policy, same payment method within 10 business days (4.1).",
        _DEFECT_NOTE,
    ),
    "shipping": (
        "Delivery in the Campo Grande metro area: quote_payment says whether it is free or R$ 35,00.",
        "Other cities: the price depends on CEP, weight and size, which this service does not have; never state a "
        "value.",
    ),
    "promotions": (
        "Only promotions active in the store system apply; search_products and get_product_details show them.",
        "The campaigns in 6.1 describe the year, they are not current offers: never promise them (7.3).",
    ),
    "warranty": (
        _DEFECT_NOTE,
        "The legal warranty runs 90 days from receipt (8.1); for a hidden defect, from when it shows up (CDC, art. "
        "26, paragraph 3). The manufacturer's warranty adds to it (8.2).",
    ),
    "privacy": ("Never share another customer's data; order details need verification (get_order_status).",),
    "contact": (),
}


def get_store_policy(ctx: ToolContext, topic: str) -> Result:
    sections = [ctx.manual.section(section_id) for section_id in TOPICS[topic]]
    if any(section is None for section in sections):
        raise ToolError("policy_unavailable", f"the manual is missing a section for {topic}")
    result: Result = {
        "topic": topic,
        "sections": [{"id": s.id, "title": s.title, "text": s.text} for s in sections],
    }
    if NOTES[topic]:
        result["notes"] = list(NOTES[topic])
    if topic in ("hours", "contact"):
        result["hours"] = HOURS_TEXT
        result.update(store_status(ctx.now()))
    if topic == "contact":
        result["contacts"] = CONTACTS
        result["company"] = COMPANY
    return result


TOOLS = (
    Tool(
        name="get_store_policy",
        description=(
            "The store's policy manual on one topic: section ids, titles and text, plus notes on how to apply them. "
            "Use it for questions about business hours, payment rules, returns and exchanges, shipping, promotions "
            "rules, warranty, privacy, contacts or what the store sells. Cite the section in the answer."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "enum": list(TOPICS), "description": "The policy topic."},
            },
            "required": ["topic"],
            "additionalProperties": False,
        },
        handler=get_store_policy,
    ),
)
