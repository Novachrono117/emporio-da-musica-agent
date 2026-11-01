"""Load the store CSVs into typed records.

The raw files in data/ are never edited. Every cleaning and validation rule applied here is documented in
docs/DATA_NOTES.md; a file that breaks one of them raises DataError instead of loading half-clean data.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType

from emporio.data.models import (
    Category,
    Customer,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    Product,
    ProductStatus,
    Promotion,
)

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
FILE_PREFIX = "desafio_tecnico_ai_eng - "
CENT = Decimal("0.01")


class DataError(ValueError):
    """The store data breaks a rule the agent relies on."""


@dataclass(frozen=True)
class StoreData:
    categories: tuple[Category, ...]
    products: tuple[Product, ...]
    promotions: tuple[Promotion, ...]
    customers: tuple[Customer, ...]
    orders: tuple[Order, ...]


def load_store_data(data_dir: Path = DATA_DIR) -> StoreData:
    items = _order_items(_read(data_dir, "order_items"))
    data = StoreData(
        categories=tuple(_category(row) for row in _read(data_dir, "categories")),
        products=tuple(_product(row) for row in _read(data_dir, "products")),
        promotions=tuple(_promotion(row) for row in _read(data_dir, "promotions")),
        customers=tuple(_customer(row) for row in _read(data_dir, "customers")),
        orders=tuple(_order(row, items) for row in _read(data_dir, "orders")),
    )
    _check_integrity(data, items)
    return data


def _read(data_dir: Path, table: str) -> list[dict[str, str]]:
    path = data_dir / f"{FILE_PREFIX}{table}.csv"
    # utf-8-sig tolerates a BOM; the current files have none.
    with open(path, encoding="utf-8-sig", newline="") as file:
        rows = [{key.strip(): (value or "").strip() for key, value in row.items()} for row in csv.DictReader(file)]
    if not rows:
        raise DataError(f"{path.name} has no rows")
    return rows


def _category(row: dict[str, str]) -> Category:
    return Category(id=_int(row, "category_id"), name=_text(row, "name"), description=_text(row, "description"))


def _product(row: dict[str, str]) -> Product:
    try:
        specs = json.loads(row["specs"]) if row["specs"] else {}
    except json.JSONDecodeError as error:
        raise DataError(f"product {row['product_id']}: specs is not valid JSON ({error})") from error
    return Product(
        id=_int(row, "product_id"),
        name=_text(row, "name"),
        category_id=_int(row, "category_id"),
        description=_text(row, "description"),
        price=_money(row, "price_brl"),
        stock=_int(row, "stock_quantity", minimum=0),
        status=_enum(ProductStatus, row, "status"),
        specs=MappingProxyType(specs),
        created_at=_date(row, "created_at"),
    )


def _promotion(row: dict[str, str]) -> Promotion:
    if row["is_active"] not in ("0", "1"):
        raise DataError(f"promotion {row['promotion_id']}: is_active must be 0 or 1, got {row['is_active']!r}")
    discount = _int(row, "discount_percent", minimum=1)
    if discount >= 100:
        raise DataError(f"promotion {row['promotion_id']}: discount_percent must be below 100, got {discount}")
    return Promotion(
        id=_int(row, "promotion_id"),
        product_id=_int(row, "product_id"),
        discount_percent=discount,
        description=_text(row, "description"),
        is_active=row["is_active"] == "1",
    )


def _customer(row: dict[str, str]) -> Customer:
    return Customer(
        id=_int(row, "customer_id"),
        name=_text(row, "name"),
        phone=_text(row, "phone"),
        email=_text(row, "email"),
        city=_text(row, "city"),
    )


def _order_items(rows: list[dict[str, str]]) -> dict[int, list[OrderItem]]:
    items: dict[int, list[OrderItem]] = {}
    for row in rows:
        item = OrderItem(product_id=_int(row, "product_id"), quantity=_int(row, "quantity", minimum=1))
        items.setdefault(_int(row, "order_id"), []).append(item)
    return items


def _order(row: dict[str, str], items: dict[int, list[OrderItem]]) -> Order:
    order_id = _int(row, "order_id")
    method, installments = _payment(row)
    return Order(
        id=order_id,
        customer_id=_int(row, "customer_id"),
        order_date=_date(row, "order_date"),
        status=_enum(OrderStatus, row, "status"),
        total=_money(row, "total_brl"),
        payment_method=method,
        installments=installments,
        tracking_code=row["tracking_code"] or None,
        estimated_delivery=_date(row, "estimated_delivery") if row["estimated_delivery"] else None,
        notes=row["notes"] or None,
        items=tuple(items.get(order_id, ())),
    )


def _payment(row: dict[str, str]) -> tuple[PaymentMethod, int]:
    """'pix', 'debit', 'boleto' are paid in full; 'credit_6x' is a credit card in 6 installments."""
    raw = row["payment_method"]
    match = re.fullmatch(r"credit_(\d{1,2})x", raw)
    if match:
        installments = int(match.group(1))
        if not 1 <= installments <= 12:
            raise DataError(f"order {row['order_id']}: {installments} installments is outside 1 to 12")
        return PaymentMethod.CREDIT, installments
    try:
        return PaymentMethod(raw), 1
    except ValueError:
        raise DataError(f"order {row['order_id']}: unknown payment method {raw!r}") from None


def _check_integrity(data: StoreData, items: dict[int, list[OrderItem]]) -> None:
    for name, ids in [
        ("category", [c.id for c in data.categories]),
        ("product", [p.id for p in data.products]),
        ("promotion", [p.id for p in data.promotions]),
        ("customer", [c.id for c in data.customers]),
        ("order", [o.id for o in data.orders]),
    ]:
        duplicates = sorted(id_ for id_, count in Counter(ids).items() if count > 1)
        if duplicates:
            raise DataError(f"duplicate {name} ids: {duplicates}")

    categories = {c.id for c in data.categories}
    products = {p.id for p in data.products}
    customers = {c.id for c in data.customers}
    orders = {o.id for o in data.orders}
    problems = [f"product {p.id}: unknown category {p.category_id}" for p in data.products if p.category_id not in categories]
    problems += [f"promotion {p.id}: unknown product {p.product_id}" for p in data.promotions if p.product_id not in products]
    problems += [f"order {o.id}: unknown customer {o.customer_id}" for o in data.orders if o.customer_id not in customers]
    problems += [f"order {o.id}: no items" for o in data.orders if not o.items]
    problems += [f"order items for unknown order {order_id}" for order_id in items if order_id not in orders]
    problems += [
        f"order {o.id}: unknown product {item.product_id}" for o in data.orders for item in o.items if item.product_id not in products
    ]
    active = Counter(p.product_id for p in data.promotions if p.is_active)
    problems += [f"product {product_id}: {count} active promotions" for product_id, count in active.items() if count > 1]
    if problems:
        raise DataError("; ".join(problems))


def _text(row: dict[str, str], column: str) -> str:
    if not row[column]:
        # Name the row by its first column (its id) only: rows may hold customer data.
        raise DataError(f"empty {column} in the row with id {next(iter(row.values()))!r}")
    return row[column]


def _int(row: dict[str, str], column: str, minimum: int | None = None) -> int:
    try:
        value = int(row[column])
    except ValueError:
        raise DataError(f"{column} is not an integer: {row[column]!r}") from None
    if minimum is not None and value < minimum:
        raise DataError(f"{column} below {minimum}: {value}")
    return value


def _money(row: dict[str, str], column: str) -> Decimal:
    try:
        value = Decimal(row[column])
    except InvalidOperation:
        raise DataError(f"{column} is not a number: {row[column]!r}") from None
    if value <= 0 or value != value.quantize(CENT):
        raise DataError(f"{column} must be positive with at most two decimals: {row[column]!r}")
    return value.quantize(CENT)


def _date(row: dict[str, str], column: str) -> date:
    try:
        return date.fromisoformat(row[column])
    except ValueError:
        raise DataError(f"{column} is not an ISO date: {row[column]!r}") from None


def _enum(enum: type, row: dict[str, str], column: str):
    try:
        return enum(row[column])
    except ValueError:
        raise DataError(f"unknown {column} {row[column]!r}") from None
