"""The queries tools may run against the store data (decision D-004).

Tools receive a StoreRepository and only call these methods, so the storage behind it can change (today the CSVs in
memory, later a database) without touching tools or agent. Methods are added one at a time, as tools need them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from emporio.data.models import Category, Customer, Order, Product, Promotion


@runtime_checkable
class StoreRepository(Protocol):
    def get_product(self, product_id: int) -> Product | None: ...

    def get_category(self, category_id: int) -> Category | None: ...

    def list_categories(self) -> Sequence[Category]: ...

    def active_promotion(self, product_id: int) -> Promotion | None: ...

    def get_customer(self, customer_id: int) -> Customer | None: ...

    def get_order(self, order_id: int) -> Order | None: ...
