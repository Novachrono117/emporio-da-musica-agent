"""StoreRepository backed by the CSVs, loaded once into memory (decision D-004)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from emporio.data.loader import DATA_DIR, StoreData, load_store_data
from emporio.data.models import Category, Customer, Order, Product, Promotion


class InMemoryStore:
    def __init__(self, data: StoreData) -> None:
        self._categories = {c.id: c for c in data.categories}
        self._products = {p.id: p for p in data.products}
        self._customers = {c.id: c for c in data.customers}
        self._orders = {o.id: o for o in data.orders}
        # The loader guarantees at most one active promotion per product.
        self._active_promotions = {p.product_id: p for p in data.promotions if p.is_active}

    @classmethod
    def from_csv(cls, data_dir: Path = DATA_DIR) -> InMemoryStore:
        return cls(load_store_data(data_dir))

    def get_product(self, product_id: int) -> Product | None:
        return self._products.get(product_id)

    def get_category(self, category_id: int) -> Category | None:
        return self._categories.get(category_id)

    def list_categories(self) -> Sequence[Category]:
        return tuple(self._categories.values())

    def active_promotion(self, product_id: int) -> Promotion | None:
        return self._active_promotions.get(product_id)

    def get_customer(self, customer_id: int) -> Customer | None:
        return self._customers.get(customer_id)

    def get_order(self, order_id: int) -> Order | None:
        return self._orders.get(order_id)
