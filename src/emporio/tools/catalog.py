"""Catalog tools: search_products and get_product_details.

Matching is plain word matching, written for 65 products: accents and case are ignored, Portuguese plurals are reduced
to the singular ("violões" finds "violão"), a word can be the start of another ("strato" finds "Stratocaster") and a
typo in a product name is tolerated. Products that are not for sale carry no price (D-005, rule 10; D-006).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from decimal import Decimal
from difflib import SequenceMatcher

from emporio.data.models import Availability, Product
from emporio.tools.base import Result, Tool, ToolContext, ToolError, brl, current_price

MAX_RESULTS = 10
CANDIDATES = 5

FOR_SALE = (Availability.AVAILABLE, Availability.LAST_UNITS)
PRICED = (*FOR_SALE, Availability.OUT_OF_STOCK)  # out of stock is temporary: the catalog price still holds

AVAILABILITY_NOTES = {
    Availability.LAST_UNITS: "Discontinued: sold while stock lasts, no reservation.",
    Availability.OUT_OF_STOCK: "Temporarily unavailable: suggest similar products that are available.",
    Availability.DISCONTINUED: "No longer sold: suggest equivalent models.",
    Availability.COMING_SOON: "Not on sale yet: no price or date can be promised.",
}

_STOPWORDS = frozenset("a as o os e de da das do dos em no na nos nas para por com um uma ate ou".split())
_PLURALS = (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"), ("ores", "or"), ("ns", "m"), ("s", ""))
# Accessories the store does not sell (sections 1 and 7.1), in the singular form _words produces.
_ACCESSORIES = frozenset({"corda", "palheta", "cabo", "case", "pedal", "amplificador"})


def search_products(
    ctx: ToolContext,
    query: str | None = None,
    category: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    in_stock_only: bool = True,
    limit: int = 5,
) -> Result:
    if not 1 <= limit <= MAX_RESULTS:
        raise ToolError("invalid_input", f"limit must be between 1 and {MAX_RESULTS}")
    if (min_price is not None and min_price < 0) or (max_price is not None and max_price < 0):
        raise ToolError("invalid_input", "prices must not be negative")
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ToolError("invalid_input", "min_price must not be greater than max_price")

    category_ids = _category_ids(ctx, category) if category else None
    rows = []
    for product in ctx.store.list_products():
        if category_ids is not None and product.category_id not in category_ids:
            continue
        if in_stock_only and product.availability not in FOR_SALE:
            continue
        price = current_price(ctx.store, product)[0] if product.availability in PRICED else None
        if (min_price is not None or max_price is not None) and price is None:
            continue
        if (min_price is not None and price < min_price) or (max_price is not None and price > max_price):
            continue
        rows.append((product, price))

    strong: dict[int, int] = {}
    if query:
        words = _words(query)
        scored = [(_score(ctx, words, product), product, price) for product, price in rows]
        best = max((anywhere for (anywhere, _), _, _ in scored), default=0)
        rows = [(product, price) for (anywhere, _), product, price in scored if anywhere == best and best > 0]
        strong = {product.id: in_name for (_, in_name), product, _ in scored}
    # Products whose name or category holds the words first, then the cheapest.
    rows.sort(key=lambda row: (-strong.get(row[0].id, 0), row[1] is None, row[1] or 0, row[0].name))

    result: Result = {"total_matches": len(rows), "products": [_summary(ctx, product) for product, _ in rows[:limit]]}
    if query and _asks_for_accessory(_words(query)):
        result["accessory_note"] = (
            "The store sells instruments only, no strings, picks, cables, cases, pedals or amplifiers (sections 1 "
            "and 7.1). If the customer wants an accessory, say so politely without naming another store; the "
            "products listed are instruments whose description mentions the word."
        )
    if not rows:
        empty_category = category_ids is not None and not any(
            product.category_id in category_ids for product in ctx.store.list_products()
        )
        result["note"] = (
            "This category has no products in the store system; do not promise restocking."
            if empty_category
            else "No product matches. Try fewer words, another category or in_stock_only false."
        )
    return result


def get_product_details(ctx: ToolContext, product_id: int | None = None, name: str | None = None) -> Result:
    if (product_id is None) == (not name):
        raise ToolError("invalid_input", "give exactly one of product_id or name")
    if product_id is not None:
        product = ctx.store.get_product(product_id)
        if product is None:
            raise ToolError("not_found", f"no product with id {product_id}")
        return {"product": _details(ctx, product)}

    words = _words(name)
    scored = sorted(
        ((_score(ctx, words, product, name_only=True), product) for product in ctx.store.list_products()),
        key=lambda row: (-row[0][0], -row[0][1], row[1].name),
    )
    best = scored[0][0] if scored else (0, 0)
    matches = [product for score, product in scored if score == best and best[0] > 0]
    if not matches:
        raise ToolError("not_found", "no product matches that name; try search_products")
    if len(matches) == 1 and best[0] == len(words):
        return {"product": _details(ctx, matches[0])}
    return {
        "match": "ambiguous",
        "message": "Several products match: ask the customer which one, or call again with product_id.",
        "candidates": [{"id": product.id, "name": product.name} for product in matches[:CANDIDATES]],
    }


def _summary(ctx: ToolContext, product: Product) -> Result:
    category = ctx.store.get_category(product.category_id)
    summary: Result = {
        "id": product.id,
        "name": product.name,
        "category": category.name if category else "",
        "availability": product.availability.value,
    }
    if product.availability in PRICED:
        price, promotion = current_price(ctx.store, product)
        summary["price"] = brl(price)
        if promotion is not None:  # 6.2: show the original price and the percentage next to the promotional one
            summary["list_price"] = brl(product.price)
            summary["promotion"] = {"name": promotion.description, "discount_percent": promotion.discount_percent}
    if product.availability in AVAILABILITY_NOTES:
        summary["availability_note"] = AVAILABILITY_NOTES[product.availability]
    return summary


def _details(ctx: ToolContext, product: Product) -> Result:
    details = _summary(ctx, product)
    details["description"] = product.description
    details["specs"] = dict(product.specs)
    if product.availability in FOR_SALE:
        details["stock"] = product.stock
    return details


def _asks_for_accessory(words: list[str]) -> bool:
    """True for "cordas" or "pedal", false for "7 cordas" (a seven-string guitar)."""
    return any(
        word in _ACCESSORIES and not (word == "corda" and index > 0 and words[index - 1].isdigit())
        for index, word in enumerate(words)
    )


def _category_ids(ctx: ToolContext, category: str) -> set[int]:
    wanted = _words(category)
    ids = {c.id for c in ctx.store.list_categories() if wanted and all(_matches(w, _words(c.name)) for w in wanted)}
    if not ids:
        names = ", ".join(c.name for c in ctx.store.list_categories())
        raise ToolError("invalid_input", f"unknown category {category!r}; categories: {names}")
    return ids


def _score(ctx: ToolContext, words: list[str], product: Product, name_only: bool = False) -> tuple[int, int]:
    """(query words found anywhere, query words found in the name or the category name).

    "Anywhere" adds the description and the spec values. Typos are tolerated in the name only.
    """
    name = _words(product.name)
    category: list[str] = []
    other: list[str] = []
    if not name_only:
        record = ctx.store.get_category(product.category_id)
        category = _words(record.name) if record else []
        other = _words(f"{product.description} {' '.join(map(str, product.specs.values()))}")
    strong = sum(1 for w in words if _matches(w, name, fuzzy=True) or _matches(w, category))
    anywhere = sum(1 for w in words if _matches(w, name, fuzzy=True) or _matches(w, category) or _matches(w, other))
    return anywhere, strong


def _matches(word: str, candidates: Iterable[str], fuzzy: bool = False) -> bool:
    for candidate in candidates:
        if word == candidate or (len(word) >= 3 and candidate.startswith(word)):
            return True
        if fuzzy and len(word) >= 4 and SequenceMatcher(None, word, candidate).ratio() >= 0.8:
            return True
    return False


def _words(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return [_singular(word) for word in re.findall(r"[a-z0-9]+", plain) if word not in _STOPWORDS]


def _singular(word: str) -> str:
    if not word.isalpha():
        return word  # model codes such as "15s" or "gd20"
    for suffix, replacement in _PLURALS:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)] + replacement
    return word


TOOLS = (
    Tool(
        name="search_products",
        description=(
            "Search the store catalog. Use it for any question about which instruments the store has, their prices, "
            "promotions or availability. Prices are final prices (promotion applied). Returns at most `limit` "
            "products, cheapest first."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words to look for, e.g. 'violão Yamaha' or 'Stratocaster'."},
                "category": {
                    "type": "string",
                    "description": "Category name, e.g. 'Violões', 'Guitarras', 'Baixos', 'Ukuleles', 'Teclados'.",
                },
                "min_price": {"type": "number", "description": "Minimum final price in BRL."},
                "max_price": {"type": "number", "description": "Maximum final price in BRL, e.g. 1000."},
                "in_stock_only": {
                    "type": "boolean",
                    "description": "Default true. Set false to also see out-of-stock, discontinued and coming-soon items.",
                },
                "limit": {"type": "integer", "description": "How many products to return, 1 to 10. Default 5."},
            },
            "required": [],
            "additionalProperties": False,
        },
        handler=search_products,
    ),
    Tool(
        name="get_product_details",
        description=(
            "Full details of one product: description, specs, price, promotion, availability and stock. Give the "
            "product_id from a search, or a name; if the name matches several products, the candidates come back."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "Product id, e.g. 95."},
                "name": {"type": "string", "description": "Product name or model, e.g. 'Takamine GD20'."},
            },
            "required": [],
            "additionalProperties": False,
        },
        handler=get_product_details,
    ),
)
