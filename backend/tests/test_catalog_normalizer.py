"""Normalizador de productos: céntimos, milésimas, packs y mostrador (F1.3)."""

from __future__ import annotations

import pytest

from app.schemas.mercadona import MercadonaProduct
from app.services.catalog_normalizer import (
    NormalizationError,
    is_food_category,
    normalize_product,
    parse_price_cents,
    quantity_to_milli,
)
from tests.catalog_fixtures import product_payload


def _product(**instruction_overrides: object) -> MercadonaProduct:
    payload = product_payload("9001", "Producto sintético")
    instructions = payload["price_instructions"]
    assert isinstance(instructions, dict)
    instructions.update(instruction_overrides)
    return MercadonaProduct.model_validate(payload)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("N/A", None),
        ("17.25", 1725),
        ("17,25", 1725),
        ("1.234,56", 123_456),
        ("1,234.56", 123_456),
        ("3.450", 345),
        ("€ 2,10", 210),
        ("1282.05", 128_205),
        ("0", 0),
    ],
)
def test_price_parsing_uses_decimal_and_cents(raw: str | None, expected: int | None) -> None:
    assert parse_price_cents(raw) == expected


@pytest.mark.parametrize("raw", ["1.2.3", "-1.00", "abc", "1e3"])
def test_invalid_prices_are_rejected(raw: str) -> None:
    with pytest.raises(NormalizationError):
        parse_price_cents(raw)


@pytest.mark.parametrize(
    ("quantity", "size_format", "expected"),
    [
        (5.0, "l", 5_000_000),
        (0.75, "kg", 750_000),
        (500.0, "g", 500_000),
        (12.0, "ud", 12_000),
        (1.0, "docena", None),
        (0.0, "g", None),
        (0.0000001, "g", None),
        (None, "g", None),
    ],
)
def test_quantity_to_milli(
    quantity: float | None, size_format: str | None, expected: int | None
) -> None:
    assert quantity_to_milli(quantity, size_format) == expected


def test_oil_bottle_is_normalized_with_package_price() -> None:
    product = MercadonaProduct.model_validate(
        product_payload(
            "9001",
            "Aceite de oliva sintético 5 L",
            unit_price="17.25",
            unit_size=5.0,
            size_format="l",
            reference_price="3.450",
            reference_format="L",
        )
    )

    normalized = normalize_product(product, category_id=112)

    assert normalized.package_price_cents == 1725
    assert normalized.package_quantity_milli == 5_000_000
    assert normalized.package_unit == "ml"
    assert normalized.reference_price_cents == 345
    assert normalized.reference_unit == "l"
    assert normalized.package_unit != "l"
    assert normalized.is_mappable is True


def test_eggs_are_counted_in_milli_units() -> None:
    product = MercadonaProduct.model_validate(
        product_payload(
            "9002",
            "Huevos frescos docena",
            unit_price="2.10",
            unit_size=12.0,
            size_format="ud",
            reference_price="0.175",
            reference_format="ud",
            packaging="Docena",
        )
    )

    normalized = normalize_product(product, category_id=6)

    assert normalized.package_price_cents == 210
    assert normalized.package_quantity_milli == 12_000
    assert normalized.package_unit == "unit"
    assert normalized.reference_price_cents == 18
    assert normalized.reference_unit == "unit"


def test_chicken_500_g_is_normalized_to_mg() -> None:
    product = MercadonaProduct.model_validate(
        product_payload(
            "9003",
            "Pechuga de pollo 500 g",
            unit_price="3.95",
            unit_size=500.0,
            size_format="g",
            reference_price="7.900",
            reference_format="kg",
        )
    )

    normalized = normalize_product(product, category_id=3)

    assert normalized.package_price_cents == 395
    assert normalized.package_quantity_milli == 500_000
    assert normalized.package_unit == "g"
    assert normalized.reference_price_cents == 790
    assert normalized.reference_unit == "kg"


def test_milk_litre_is_normalized_to_microlitres() -> None:
    product = MercadonaProduct.model_validate(
        product_payload(
            "9004",
            "Leche entera 1 L",
            unit_price="0.95",
            unit_size=1.0,
            size_format="l",
        )
    )

    normalized = normalize_product(product, category_id=6)

    assert normalized.package_price_cents == 95
    assert normalized.package_quantity_milli == 1_000_000
    assert normalized.package_unit == "ml"


def test_pack_6_by_125_g_uses_total_package_quantity() -> None:
    product = MercadonaProduct.model_validate(
        product_payload(
            "9005",
            "Pack 6 × 125 g sintético",
            unit_price="4.50",
            unit_size=750.0,
            size_format="g",
            reference_price="6.000",
            reference_format="kg",
            is_pack=True,
            pack_size=6,
            total_units=6,
        )
    )

    normalized = normalize_product(product, category_id=112)

    assert normalized.is_pack is True
    assert normalized.package_price_cents == 450
    assert normalized.package_quantity_milli == 750_000
    assert normalized.package_unit == "g"
    assert normalized.is_estimated is False


def test_pack_without_unit_size_derives_quantity_and_marks_it_estimated() -> None:
    product = MercadonaProduct.model_validate(
        product_payload(
            "9006",
            "Pack derivado",
            unit_price="4.50",
            unit_size=None,
            size_format="g",
            is_pack=True,
            pack_size=125,
            total_units=6,
        )
    )

    normalized = normalize_product(product, category_id=112)

    assert normalized.package_quantity_milli == 750_000
    assert normalized.is_estimated is True


def test_unknown_format_keeps_product_but_cannot_be_mapped() -> None:
    product = MercadonaProduct.model_validate(
        product_payload(
            "9007",
            "Producto sin formato reconocido",
            unit_price="1.00",
            unit_size=1.0,
            size_format="docena",
        )
    )

    normalized = normalize_product(product, category_id=1)

    assert normalized.package_quantity_milli is None
    assert normalized.package_unit is None
    assert normalized.is_mappable is False


def test_counter_and_variable_weight_products_are_detected() -> None:
    approx = normalize_product(
        _product(approx_size=True, selling_method=0),
        category_id=2,
    )
    counter = normalize_product(
        _product(approx_size=False, selling_method=1),
        category_id=2,
    )

    assert approx.is_counter_product is True
    assert counter.is_counter_product is True
    assert approx.is_mappable is False
    assert counter.is_mappable is False


def test_malformed_price_is_reported_with_product_context() -> None:
    product = MercadonaProduct.model_validate(
        product_payload("9008", "Producto roto", unit_price="1.2.3")
    )

    with pytest.raises(NormalizationError, match="9008"):
        normalize_product(product, category_id=1)


def test_reference_price_falls_back_to_bulk_price() -> None:
    product = MercadonaProduct.model_validate(
        product_payload(
            "9009",
            "Producto con bulk price",
            unit_price="2.00",
            unit_size=500.0,
            size_format="g",
            bulk_price="4.000",
            reference_format="kg",
        )
    )

    normalized = normalize_product(product, category_id=1)

    assert normalized.reference_price_cents == 400
    assert normalized.reference_unit == "kg"


@pytest.mark.parametrize(
    ("name", "level", "parent_is_food", "expected"),
    [
        ("Limpieza y hogar", 0, True, False),
        ("Cuidado del cabello", 0, True, False),
        ("Mascotas", 0, True, False),
        ("Fruta y verdura", 0, True, True),
        ("Bebé", 0, True, True),
        ("Alimentación infantil", 1, True, True),
        ("Toallitas y pañales", 1, True, False),
        ("Higiene y cuidado", 1, True, False),
        ("Aceite de oliva", 1, True, True),
        ("Aceite de oliva", 1, False, False),
    ],
)
def test_food_category_heuristics(
    name: str, level: int, parent_is_food: bool, expected: bool
) -> None:
    assert is_food_category(name, level=level, parent_is_food=parent_is_food) is expected
