"""Comprueba el cliente de Mercadona contra la API real.

Uso desde la raíz del repositorio:

    backend\\.venv\\Scripts\\python.exe scripts\\check_mercadona.py

o desde `backend/`:

    uv run python ..\\scripts\\check_mercadona.py

Fija el CP 22002, exige que la API confirme el almacén 4389 y muestra el árbol de
secciones y una subcategoría con un producto parseado. No descarga el catálogo
completo, no guarda respuestas y no automatiza ninguna compra.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.mercadona_client import MercadonaClient, MercadonaError  # noqa: E402


async def main() -> int:
    async with MercadonaClient() as client:
        sections = await client.get_sections()
        subcategories = [
            (section.name, subcategory)
            for section in sections
            for subcategory in section.categories
        ]

        print(f"Secciones: {len(sections)}")
        print(f"Subcategorías: {len(subcategories)}")
        print(f"Almacén confirmado: {client.warehouse}")
        print(f"CP confirmado: {client.postal_code_header}")

        if not subcategories:
            print("ERROR: no se han encontrado subcategorías.")
            return 1

        section_name, subcategory = subcategories[0]
        detail = await client.get_subcategory(subcategory.id)
        products = detail.all_products()

        print(
            f"Subcategoría de prueba: {subcategory.name} "
            f"(id {subcategory.id}, sección {section_name})"
        )
        print(f"Productos: {len(products)}")

        if not products:
            print("ERROR: no se ha podido parsear ningún producto.")
            return 1

        product = products[0]
        price = product.price_instructions
        print(f"Producto de ejemplo: {product.display_name}")
        print(f"  id: {product.id}")
        if price is not None:
            print(f"  precio del paquete: {price.unit_price}")
            print(f"  formato: {price.unit_size} {price.size_format}")
            print(f"  referencia: {price.reference_price} / {price.reference_format}")

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
    except MercadonaError as error:
        print(f"ERROR [{error.code}]: {error}", file=sys.stderr)
        exit_code = 1
    raise SystemExit(exit_code)
