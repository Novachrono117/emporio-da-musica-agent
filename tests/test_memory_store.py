"""InMemoryStore: the StoreRepository the tools use today (decision D-004)."""

from decimal import Decimal

import pytest

from emporio.data.memory import InMemoryStore
from emporio.data.repository import StoreRepository


@pytest.fixture(scope="module")
def store():
    return InMemoryStore.from_csv()


def test_it_implements_the_repository_interface(store):
    assert isinstance(store, StoreRepository)


def test_lookups_by_id(store):
    assert (store.get_product(81).name, store.get_product(81).price) == ("Yamaha C40 Nylon Natural", Decimal("599.90"))
    assert store.get_category(5).name == "Violões"
    assert store.get_customer(1).phone_last4 == "3456"
    assert store.get_order(8).tracking_code == "BRJL5544332BR"
    assert len(store.list_categories()) == 9
    assert len(store.list_products()) == 65


def test_unknown_ids_return_none(store):
    assert store.get_product(1) is None
    assert store.get_category(99) is None
    assert store.get_customer(999) is None
    assert store.get_order(0) is None


def test_active_promotion_ignores_expired_ones(store):
    promotion = store.active_promotion(127)
    assert (promotion.discount_percent, promotion.description) == (10, "Oferta Especial")
    assert store.active_promotion(93) is None  # product 93 has promotions, none active
    assert store.active_promotion(81) is None
