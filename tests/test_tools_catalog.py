"""search_products and get_product_details against the real catalog (PLAN section 7; D-005, rule 10; D-006)."""

from decimal import Decimal

import pytest

from emporio.tools.base import ToolError
from emporio.tools.catalog import get_product_details, search_products


def _ids(result):
    return [p["id"] for p in result["products"]]


def test_price_filter_uses_the_final_price_and_sorts_cheapest_first(ctx):
    result = search_products(ctx, category="violões", max_price=Decimal("600"), limit=10)
    assert _ids(result) == [83, 85, 89, 88, 81]  # 96 (R$ 799,90) is out of stock and above the limit anyway
    # Product 121 lists at R$ 549,00 with 20% off: R$ 439,20 is inside the range, R$ 549,00 would not be.
    ukuleles = search_products(ctx, category="ukulele", min_price=Decimal("430"), max_price=Decimal("440"))
    assert _ids(ukuleles) == [121]


def test_promotion_shows_original_price_and_percentage(ctx):
    [product] = search_products(ctx, query="Ohana CK-20")["products"]
    assert product["price"] == "R$ 439,20"
    assert product["list_price"] == "R$ 549,00"
    assert product["promotion"] == {"name": "Desconto Exclusivo", "discount_percent": 20}


def test_products_without_promotion_have_one_price(ctx):
    [product] = search_products(ctx, query="Takamine GD20")["products"]
    assert product["price"] == "R$ 2.199,00"
    assert "list_price" not in product and "promotion" not in product


def test_query_matches_category_plural_and_accents(ctx):
    result = search_products(ctx, query="violoes yamaha", limit=10)
    assert _ids(result) == [81, 87, 82, 92, 114, 104, 98]
    assert all(p["name"].startswith("Yamaha") and p["category"] == "Violões" for p in result["products"])


def test_name_and_category_matches_come_before_description_matches(ctx):
    # The baritone ukulele 128 mentions "violão" in its description; the guitars come first.
    result = search_products(ctx, query="violão", max_price=Decimal("1000"), limit=10)
    assert result["total_matches"] == 13
    assert 128 not in _ids(result)


def test_out_of_stock_items_only_when_asked(ctx):
    assert 96 not in _ids(search_products(ctx, query="Giannini GF-3D"))
    [product] = search_products(ctx, query="Giannini GF-3D", in_stock_only=False)["products"]
    assert product["availability"] == "out_of_stock"
    assert product["price"] == "R$ 799,90"
    assert "suggest similar" in product["availability_note"]


def test_products_not_for_sale_carry_no_price(ctx):
    coming_soon = get_product_details(ctx, product_id=130)["product"]
    assert coming_soon["availability"] == "coming_soon"
    assert "price" not in coming_soon and "stock" not in coming_soon
    discontinued = get_product_details(ctx, product_id=113)["product"]
    assert discontinued["availability"] == "discontinued"
    assert "price" not in discontinued


def test_last_units_are_sold_without_reservation(ctx):
    product = get_product_details(ctx, product_id=136)["product"]
    assert (product["availability"], product["price"], product["stock"]) == ("last_units", "R$ 441,00", 13)
    assert "no reservation" in product["availability_note"]


def test_empty_category_says_so_without_promising_restock(ctx):
    result = search_products(ctx, category="sopro")
    assert result["products"] == []
    assert "no products in the store system" in result["note"]


def test_unknown_category_lists_the_real_ones(ctx):
    with pytest.raises(ToolError, match="categories: Guitarras, Baixos"):
        search_products(ctx, category="harpas")


def test_accessory_words_add_a_note(ctx):
    assert "instruments only" in search_products(ctx, query="cordas de violão")["accessory_note"]
    assert "accessory_note" in search_products(ctx, query="amplificadores")
    assert "accessory_note" not in search_products(ctx, query="violão 7 cordas")


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"limit": 0}, "limit must be between 1 and 10"),
        ({"min_price": Decimal("-1")}, "must not be negative"),
        ({"min_price": Decimal("900"), "max_price": Decimal("100")}, "min_price must not be greater"),
    ],
)
def test_search_rejects_bad_ranges(ctx, kwargs, message):
    with pytest.raises(ToolError, match=message):
        search_products(ctx, **kwargs)


def test_details_by_name_tolerate_typos(ctx):
    assert get_product_details(ctx, name="Takamine GD20")["product"]["id"] == 95
    assert get_product_details(ctx, name="fender stratocastr")["product"]["id"] == 145


def test_details_carry_description_specs_and_stock(ctx):
    product = get_product_details(ctx, product_id=81)["product"]
    assert product["name"] == "Yamaha C40 Nylon Natural"
    assert product["specs"]["top"] == "Spruce"
    assert product["stock"] == 12
    assert product["description"].startswith("Violão clássico")


def test_contradictory_descriptions_are_neither_shown_nor_searched(ctx):
    # 142 is a "Korg" whose raw description describes an 88-key Roland; 135 a "Music Man" described as a Fender.
    product = get_product_details(ctx, product_id=142)["product"]
    assert "description" not in product
    assert product["specs"]["keys"] == "61"
    assert _ids(search_products(ctx, query="Fender")) == [134, 145]
    assert _ids(search_products(ctx, query="Roland")) == [144]


def test_ambiguous_name_returns_candidates_instead_of_guessing(ctx):
    result = get_product_details(ctx, name="Kala")
    assert result["match"] == "ambiguous"
    assert len(result["candidates"]) == 5
    assert all(c["name"].startswith("Kala ") for c in result["candidates"])


def test_details_need_exactly_one_identifier(ctx):
    with pytest.raises(ToolError, match="exactly one"):
        get_product_details(ctx)
    with pytest.raises(ToolError, match="exactly one"):
        get_product_details(ctx, product_id=81, name="Yamaha")
    with pytest.raises(ToolError) as error:
        get_product_details(ctx, product_id=1)
    assert error.value.code == "not_found"
    with pytest.raises(ToolError, match="no product matches"):
        get_product_details(ctx, name="Stradivarius")
