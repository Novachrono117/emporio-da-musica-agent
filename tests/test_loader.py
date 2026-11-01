"""Loading the store CSVs: counts, types, cleaning rules and the integrity checks."""

import csv
import re
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from emporio.data.loader import DATA_DIR, FILE_PREFIX, DataError, load_store_data
from emporio.data.models import Availability, OrderStatus, PaymentMethod


@pytest.fixture(scope="module")
def data():
    return load_store_data()


@pytest.fixture
def data_copy(tmp_path) -> Path:
    for path in DATA_DIR.glob("*.csv"):
        shutil.copy(path, tmp_path / path.name)
    return tmp_path


def _rewrite(data_dir: Path, table: str, change) -> None:
    path = data_dir / f"{FILE_PREFIX}{table}.csv"
    with open(path, encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    change(rows)
    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_row_counts_match_the_files(data):
    counts = (len(data.categories), len(data.products), len(data.promotions), len(data.customers), len(data.orders))
    assert counts == (9, 65, 25, 50, 20)
    assert sum(len(order.items) for order in data.orders) == 22


def test_product_ids_run_from_81_to_145(data):
    assert sorted(p.id for p in data.products) == list(range(81, 146))


def test_money_is_decimal_with_two_places(data):
    amounts = [p.price for p in data.products] + [o.total for o in data.orders]
    assert all(isinstance(a, Decimal) and a.as_tuple().exponent == -2 for a in amounts)
    assert min(p.price for p in data.products) == Decimal("159.90")


def test_specs_are_parsed_from_json(data):
    product = next(p for p in data.products if p.id == 81)
    assert product.specs["strings"] == "nylon"


def test_payment_method_is_split_into_method_and_installments(data):
    orders = {o.id: o for o in data.orders}
    assert (orders[3].payment_method, orders[3].installments) == (PaymentMethod.CREDIT, 12)
    assert (orders[1].payment_method, orders[1].installments) == (PaymentMethod.PIX, 1)


def test_empty_optional_fields_become_none(data):
    orders = {o.id: o for o in data.orders}
    assert orders[8].tracking_code == "BRJL5544332BR"
    assert orders[8].estimated_delivery == date(2026, 2, 28)
    assert (orders[13].tracking_code, orders[13].estimated_delivery, orders[13].notes) == (None, None, None)


def test_only_shipped_and_delivered_orders_have_tracking(data):
    for order in data.orders:
        shipped = order.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED)
        assert (order.tracking_code is not None) == shipped == (order.estimated_delivery is not None)
        if order.tracking_code:
            assert re.fullmatch(r"BR[A-Z0-9]{9}BR", order.tracking_code)  # manual 5.3


def test_recorded_totals_are_kept_even_when_they_differ_from_the_items(data):
    orders = {o.id: o for o in data.orders}
    assert orders[3].total == Decimal("3450.00")  # items at list price: 3498.00
    assert orders[20].total == Decimal("1400.00")  # items at list price: 1488.00


def test_availability_combines_status_and_stock(data):
    products = {p.id: p for p in data.products}
    assert products[81].availability is Availability.AVAILABLE
    assert products[96].availability is Availability.OUT_OF_STOCK  # active, stock 0
    assert products[113].availability is Availability.DISCONTINUED  # discontinued, stock 0
    assert products[136].availability is Availability.LAST_UNITS  # discontinued, stock 13
    assert products[130].availability is Availability.COMING_SOON  # coming soon, stock 2


def test_contradictory_descriptions_are_dropped_and_the_rest_kept(data):
    products = {p.id: p for p in data.products}
    with open(DATA_DIR / f"{FILE_PREFIX}products.csv", encoding="utf-8", newline="") as file:
        raw = {int(row["product_id"]): row["description"] for row in csv.DictReader(file)}
    dropped = [135, 136, 137, 139, 140, 142, 144]
    assert all(products[i].description == "" and raw[i] for i in dropped)  # the raw file keeps them
    assert "Fender Jazz Bass" in raw[135] and "Music Man" in products[135].name
    assert all(products[i].description == raw[i] for i in products if i not in dropped)


def test_three_categories_have_no_products(data):
    used = {p.category_id for p in data.products}
    assert sorted(c.id for c in data.categories if c.id not in used) == [6, 7, 8]


def test_a_bom_is_tolerated(data_copy):
    path = data_copy / f"{FILE_PREFIX}categories.csv"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert len(load_store_data(data_copy).categories) == 9


def test_unknown_product_in_an_order_is_rejected(data_copy):
    _rewrite(data_copy, "order_items", lambda rows: rows[0].update(product_id="999"))
    with pytest.raises(DataError, match="unknown product 999"):
        load_store_data(data_copy)


def test_two_active_promotions_for_one_product_are_rejected(data_copy):
    def duplicate_active(rows):
        active = next(r for r in rows if r["is_active"] == "1")
        rows.append({**active, "promotion_id": "99"})

    _rewrite(data_copy, "promotions", duplicate_active)
    with pytest.raises(DataError, match="2 active promotions"):
        load_store_data(data_copy)


def test_duplicate_ids_are_rejected(data_copy):
    _rewrite(data_copy, "products", lambda rows: rows.append(dict(rows[0])))
    with pytest.raises(DataError, match="duplicate product ids"):
        load_store_data(data_copy)


def test_invalid_specs_json_is_rejected(data_copy):
    _rewrite(data_copy, "products", lambda rows: rows[0].update(specs="{not json"))
    with pytest.raises(DataError, match="specs is not valid JSON"):
        load_store_data(data_copy)


def test_prices_with_more_than_two_decimals_are_rejected(data_copy):
    _rewrite(data_copy, "products", lambda rows: rows[0].update(price_brl="10.999"))
    with pytest.raises(DataError, match="at most two decimals"):
        load_store_data(data_copy)


def test_unknown_order_status_is_rejected(data_copy):
    _rewrite(data_copy, "orders", lambda rows: rows[0].update(status="lost"))
    with pytest.raises(DataError, match="unknown status 'lost'"):
        load_store_data(data_copy)


def test_errors_do_not_echo_customer_data(data_copy):
    def blank_name(rows):
        rows[0]["name"] = ""

    _rewrite(data_copy, "customers", blank_name)
    with pytest.raises(DataError) as error:
        load_store_data(data_copy)
    assert "@" not in str(error.value) and "(67)" not in str(error.value)
