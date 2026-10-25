"""Spike del catálogo completo de Mercadona (F0.5).

Descarga todas las subcategorías con concurrencia 4 y calcula métricas del catálogo
sin guardar productos ni el JSON original. No automatiza ninguna compra.

Uso desde la raíz del repositorio:

    backend\\.venv\\Scripts\\python.exe scripts\\spike_catalog.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.mercadona import MercadonaProduct, MercadonaSubcategory  # noqa: E402
from app.services.mercadona_client import MercadonaClient, MercadonaError  # noqa: E402

CONCURRENCY = 4
REFERENCE_UNIQUE_PRODUCTS = 4327

MIN_SECTIONS = 20
MIN_SUBCATEGORIES = 100
MIN_UNIQUE_PRODUCTS = 3000
MIN_PARSEABLE_PRICES = 3000


@dataclass
class ProductFlags:
    """Datos mínimos por producto único; no se conserva el producto completo."""

    published: bool = True
    price_missing: bool = False
    price_invalid: bool = False
    size_missing: bool = False
    approx_size: bool = False
    variant_id: bool = False


@dataclass
class SubcategoryResult:
    subcategory_id: int
    name: str
    products_seen: int = 0
    flags: dict[str, ProductFlags] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


def parse_price(value: str | None) -> Decimal | None:
    """Convierte un precio textual de Mercadona a Decimal, o None si no es válido."""
    if value is None:
        return None
    normalized = value.strip().replace(" ", "").replace(",", ".")
    if not normalized:
        return None
    try:
        price = Decimal(normalized)
    except InvalidOperation:
        return None
    return price if price >= 0 else None


def product_flags(product: MercadonaProduct) -> ProductFlags:
    price = product.price_instructions
    raw_price = price.unit_price if price is not None else None
    parsed_price = parse_price(raw_price)
    return ProductFlags(
        published=product.published,
        price_missing=raw_price is None or not raw_price.strip(),
        price_invalid=bool(raw_price and raw_price.strip()) and parsed_price is None,
        size_missing=price is None or price.unit_size is None or not price.size_format,
        approx_size=price is not None and bool(price.approx_size),
        variant_id=not product.id.isdigit(),
    )


async def download_subcategory(
    client: MercadonaClient,
    semaphore: asyncio.Semaphore,
    subcategory: MercadonaSubcategory,
) -> SubcategoryResult:
    result = SubcategoryResult(subcategory_id=subcategory.id, name=subcategory.name)

    async with semaphore:
        try:
            detail = await client.get_subcategory(subcategory.id)
        except MercadonaError as error:
            result.error_code = error.code
            result.error_message = error.message
            return result

    products = detail.all_products()
    result.products_seen = len(products)
    for product in products:
        result.flags[product.id] = product_flags(product)
    return result


def merge_flags(
    unique_products: dict[str, ProductFlags],
    new_flags: dict[str, ProductFlags],
) -> None:
    """Une por `id`; si un producto aparece en dos subcategorías, vale el primero."""
    for product_id, flags in new_flags.items():
        unique_products.setdefault(product_id, flags)


def print_check(label: str, passed: bool) -> None:
    status = "OK" if passed else "FALLO"
    print(f"  [{status}] {label}")


async def main() -> int:
    started = time.perf_counter()

    async with MercadonaClient() as client:
        sections = await client.get_sections()
        subcategories = [
            subcategory
            for section in sections
            for subcategory in section.categories
        ]

        print("=== Spike del catalogo de Mercadona (F0.5) ===")
        print(f"Almacen confirmado: {client.warehouse}")
        print(f"CP confirmado: {client.postal_code_header}")
        print(f"Concurrencia: {CONCURRENCY}")

        if not subcategories:
            print("ERROR: no se han encontrado subcategorias.")
            return 1

        semaphore = asyncio.Semaphore(CONCURRENCY)
        tasks = [
            download_subcategory(client, semaphore, subcategory)
            for subcategory in subcategories
        ]
        results = await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - started

    failures = [result for result in results if result.error_code is not None]
    unique_products: dict[str, ProductFlags] = {}
    product_entries = 0
    for result in results:
        product_entries += result.products_seen
        merge_flags(unique_products, result.flags)

    unique = len(unique_products)
    missing_price = sum(1 for flags in unique_products.values() if flags.price_missing)
    invalid_price = sum(1 for flags in unique_products.values() if flags.price_invalid)
    unpublished = sum(1 for flags in unique_products.values() if not flags.published)
    missing_size = sum(1 for flags in unique_products.values() if flags.size_missing)
    approx_size = sum(1 for flags in unique_products.values() if flags.approx_size)
    variant_ids = sum(1 for flags in unique_products.values() if flags.variant_id)
    parseable_price = unique - missing_price - invalid_price
    reference_delta = unique - REFERENCE_UNIQUE_PRODUCTS
    reference_percent = (unique / REFERENCE_UNIQUE_PRODUCTS - 1) * 100

    print()
    print("--- Cobertura ---")
    print(f"Secciones: {len(sections)}")
    print(f"Subcategorias: {len(subcategories)}")
    print(f"Subcategorias descargadas: {len(results) - len(failures)}")
    print(f"Subcategorias fallidas: {len(failures)}")
    for failure in failures:
        print(
            f"  - {failure.subcategory_id} {failure.name}: "
            f"[{failure.error_code}] {failure.error_message}"
        )

    print()
    print("--- Productos ---")
    print(f"Productos vistos (con duplicados): {product_entries}")
    print(f"Productos unicos: {unique}")
    print(f"  con precio parseable: {parseable_price}")
    print(f"  sin precio: {missing_price}")
    print(f"  con precio no parseable: {invalid_price}")
    print(f"  no publicados: {unpublished}")
    print(f"  sin tamano o formato de paquete: {missing_size}")
    print(f"  con peso aproximado (approx_size): {approx_size}")
    print(f"  con id de variante (no numerico): {variant_ids}")
    print(
        f"Referencia observada: ~{REFERENCE_UNIQUE_PRODUCTS}; "
        f"diferencia: {reference_delta:+d} ({reference_percent:+.1f} %)"
    )

    print()
    print("--- Tiempo ---")
    print(f"Total: {elapsed:.2f} s")

    checks = [
        (f"Secciones >= {MIN_SECTIONS}", len(sections) >= MIN_SECTIONS),
        (f"Subcategorias >= {MIN_SUBCATEGORIES}", len(subcategories) >= MIN_SUBCATEGORIES),
        (f"Productos unicos >= {MIN_UNIQUE_PRODUCTS}", unique >= MIN_UNIQUE_PRODUCTS),
        (
            f"Productos con precio parseable >= {MIN_PARSEABLE_PRICES}",
            parseable_price >= MIN_PARSEABLE_PRICES,
        ),
        ("Sin precios no parseables", invalid_price == 0),
    ]

    print()
    print("--- Umbrales (F0.5) ---")
    for label, passed in checks:
        print_check(label, passed)
    if failures:
        print(
            f"  [AVISO] {len(failures)} subcategorias fallidas: "
            "el informe es parcial y conviene repetir el spike."
        )

    all_passed = all(passed for _, passed in checks)
    print()
    print(f"Resultado: {'APTO' if all_passed else 'NO APTO'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
    except MercadonaError as error:
        print(f"ERROR [{error.code}]: {error}", file=sys.stderr)
        exit_code = 1
    raise SystemExit(exit_code)
