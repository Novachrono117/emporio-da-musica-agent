"""Typed records for the store data. Money is always a Decimal in BRL with two decimal places."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class ProductStatus(StrEnum):
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    COMING_SOON = "coming_soon"


class Availability(StrEnum):
    AVAILABLE = "available"
    LAST_UNITS = "last_units"  # discontinued, sold while stock lasts
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"
    COMING_SOON = "coming_soon"


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentMethod(StrEnum):
    PIX = "pix"
    DEBIT = "debit"
    CREDIT = "credit"
    BOLETO = "boleto"


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    description: str


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    category_id: int
    description: str  # empty when dropped as contradictory (see docs/DATA_NOTES.md)
    price: Decimal
    stock: int
    status: ProductStatus
    specs: Mapping[str, object] = field(hash=False)
    created_at: date

    @property
    def availability(self) -> Availability:
        if self.status is ProductStatus.COMING_SOON:
            return Availability.COMING_SOON
        if self.status is ProductStatus.DISCONTINUED:
            return Availability.LAST_UNITS if self.stock > 0 else Availability.DISCONTINUED
        return Availability.AVAILABLE if self.stock > 0 else Availability.OUT_OF_STOCK


@dataclass(frozen=True)
class Promotion:
    id: int
    product_id: int
    discount_percent: int
    description: str
    is_active: bool


@dataclass(frozen=True)
class Customer:
    id: int
    name: str
    phone: str
    email: str
    city: str

    @property
    def phone_last4(self) -> str:
        return "".join(ch for ch in self.phone if ch.isdigit())[-4:]


@dataclass(frozen=True)
class OrderItem:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class Order:
    id: int
    customer_id: int
    order_date: date
    status: OrderStatus
    total: Decimal  # as recorded; never recomputed from the items (see docs/DATA_NOTES.md)
    payment_method: PaymentMethod
    installments: int  # 1 unless paid by credit card in installments
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None
    items: tuple[OrderItem, ...]
