"""Constructores de payloads sintéticos para los tests de catálogo."""

from __future__ import annotations

from typing import Any

from app.schemas.mercadona import (
    MercadonaCategoryDetail,
    MercadonaSection,
    MercadonaSubcategory,
)


def product_payload(
    product_id: str,
    name: str,
    *,
    unit_price: str | None = "1.00",
    unit_size: float | None = 1.0,
    size_format: str | None = "l",
    reference_price: str | None = None,
    reference_format: str | None = None,
    bulk_price: str | None = None,
    is_pack: bool = False,
    pack_size: float | None = None,
    total_units: int | None = None,
    approx_size: bool = False,
    selling_method: int = 0,
    published: bool = True,
    ean: str | None = None,
    packaging: str | None = None,
    brand: str | None = None,
) -> dict[str, Any]:
    """Producto con la forma que devuelve la API de Mercadona."""
    return {
        "id": product_id,
        "display_name": name,
        "ean": ean,
        "brand": brand,
        "packaging": packaging,
        "published": published,
        "thumbnail": f"https://example.invalid/{product_id}.jpg",
        "price_instructions": {
            "unit_price": unit_price,
            "unit_size": unit_size,
            "size_format": size_format,
            "reference_price": reference_price,
            "reference_format": reference_format,
            "bulk_price": bulk_price,
            "is_pack": is_pack,
            "pack_size": pack_size,
            "total_units": total_units,
            "approx_size": approx_size,
            "selling_method": selling_method,
        },
    }


def detail_payload(
    subcategory_id: int,
    subcategory_name: str,
    products: list[dict[str, Any]],
) -> MercadonaCategoryDetail:
    return MercadonaCategoryDetail.model_validate(
        {
            "id": subcategory_id,
            "name": subcategory_name,
            "products": [],
            "categories": [
                {
                    "id": subcategory_id + 10_000,
                    "name": f"Grupo de {subcategory_name}",
                    "products": products,
                }
            ],
        }
    )


def section_payload(
    section_id: int,
    section_name: str,
    subcategories: list[MercadonaSubcategory],
    *,
    order: int = 1,
) -> MercadonaSection:
    return MercadonaSection.model_validate(
        {
            "id": section_id,
            "name": section_name,
            "order": order,
            "categories": [
                {"id": subcategory.id, "name": subcategory.name, "order": order}
                for subcategory in subcategories
            ],
        }
    )
