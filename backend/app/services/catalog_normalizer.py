"""Normalización del catálogo de Mercadona (F1.3).

Reglas:

- El dinero se convierte a céntimos enteros con `Decimal`; nunca con `float`.
- Las cantidades se convierten a milésimas de la unidad base: mg, µl o
  mili-unidades. `package_unit` guarda la unidad base (`g`, `ml` o `unit`).
- `unit_price` de la API es el precio del paquete, no el precio por unidad base.
- Los formatos desconocidos se dejan como `None`: el producto existe en el
  catálogo, pero F2.3 no podrá mapearlo a un ingrediente.
- Los productos de mostrador o de peso variable (`approx_size` o
  `selling_method != 0`) se detectan y no serán mapeables.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.schemas.mercadona import MercadonaProduct

_CENT = Decimal("1")
_VALID_PRICE = re.compile(r"-?[0-9][0-9.,]*")

#: factor para pasar la cantidad a milésimas de la unidad base.
_SIZE_FORMATS: dict[str, tuple[str, int]] = {
    "g": ("g", 1_000),
    "gr": ("g", 1_000),
    "gramo": ("g", 1_000),
    "gramos": ("g", 1_000),
    "mg": ("g", 1),
    "kg": ("g", 1_000_000),
    "kilogramo": ("g", 1_000_000),
    "kilogramos": ("g", 1_000_000),
    "ml": ("ml", 1_000),
    "mililitro": ("ml", 1_000),
    "mililitros": ("ml", 1_000),
    "cl": ("ml", 10_000),
    "l": ("ml", 1_000_000),
    "lt": ("ml", 1_000_000),
    "litro": ("ml", 1_000_000),
    "litros": ("ml", 1_000_000),
    "ud": ("unit", 1_000),
    "uds": ("unit", 1_000),
    "u": ("unit", 1_000),
    "unidad": ("unit", 1_000),
    "unidades": ("unit", 1_000),
}

#: Unidad de referencia admitida por la API (`reference_format`).
_REFERENCE_UNITS: dict[str, str] = {
    "g": "g",
    "gr": "g",
    "gramo": "g",
    "gramos": "g",
    "kg": "kg",
    "kilogramo": "kg",
    "kilogramos": "kg",
    "ml": "ml",
    "mililitro": "ml",
    "mililitros": "ml",
    "l": "l",
    "lt": "l",
    "litro": "l",
    "litros": "l",
    "ud": "unit",
    "uds": "unit",
    "u": "unit",
    "unidad": "unit",
    "unidades": "unit",
}

_NON_FOOD_SECTION_TOKENS: tuple[str, ...] = (
    "cuidado del cabello",
    "cuidado facial",
    "fitoterapia",
    "parafarmacia",
    "limpieza",
    "maquillaje",
    "mascotas",
)
_NON_FOOD_SUBCATEGORY_TOKENS: tuple[str, ...] = (
    "biberon",
    "chupete",
    "higiene",
    "toallita",
    "panal",
    "papel higienico",
    "detergente",
    "suavizante",
    "limpieza",
    "lavavajillas",
    "fregasuelos",
    "bolsas de basura",
)


class NormalizationError(ValueError):
    """El producto trae un importe o formato que no se puede normalizar."""


@dataclass(frozen=True, slots=True)
class NormalizedProduct:
    """Producto listo para persistir, sin `raw_json` ni detalle de la API."""

    external_id: str
    name: str
    ean: str | None
    brand: str | None
    category_id: int
    packaging: str | None
    package_quantity_milli: int | None
    package_unit: str | None
    is_estimated: bool
    package_price_cents: int | None
    reference_price_cents: int | None
    reference_unit: str | None
    is_pack: bool
    approx_size: bool
    selling_method: int | None
    thumbnail_url: str | None
    published: bool
    unavailable_from: str | None

    @property
    def is_counter_product(self) -> bool:
        """Producto de mostrador o de peso variable, fuera del mapeo del MVP."""
        return self.approx_size or self.selling_method not in (None, 0)

    @property
    def is_mappable(self) -> bool:
        """Puede usarse para mapear un ingrediente a un producto comprable."""
        return (
            self.published
            and not self.is_counter_product
            and self.package_price_cents is not None
            and self.package_quantity_milli is not None
            and self.package_unit is not None
        )


def normalize_token(value: str) -> str:
    """Pasa a minúsculas, quita acentos y espacios sobrantes."""
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(without_accents.casefold().split())


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned[:limit] or None


def parse_price_cents(raw: str | None) -> int | None:
    """Convierte un importe de la API a céntimos enteros.

    Acepta coma o punto decimal y símbolos de moneda. Un valor vacío o formado
    solo por símbolos se interpreta como «sin precio».
    """
    if raw is None:
        return None

    text = raw.strip()
    if not text or text.casefold() in {"n/a", "na", "-"}:
        return None
    cleaned = text.replace("€", "").replace(" ", "").replace("\u00a0", "")
    if not cleaned:
        return None
    if _VALID_PRICE.fullmatch(cleaned) is None:
        raise NormalizationError(f"Importe no válido: {raw!r}")
    if cleaned.count("-") > 0:
        raise NormalizationError(f"Importe negativo no válido: {raw!r}")
    if cleaned.count(",") > 0 and cleaned.count(".") > 0:
        decimal_separator = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        cleaned = cleaned.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")

    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise NormalizationError(f"Importe no válido: {raw!r}") from exc

    if not amount.is_finite():
        raise NormalizationError(f"Importe no finito: {raw!r}")
    if amount < 0:
        raise NormalizationError(f"Importe negativo no válido: {raw!r}")
    return int((amount * 100).quantize(_CENT, rounding=ROUND_HALF_UP))


def _format_factor(size_format: str | None) -> tuple[str, int] | None:
    if size_format is None:
        return None
    return _SIZE_FORMATS.get(normalize_token(size_format))


def quantity_to_milli(quantity: float | int | None, size_format: str | None) -> int | None:
    """Convierte una cantidad de la API a milésimas de unidad base.

    Devuelve `None` si falta la cantidad o el formato no se reconoce.
    """
    if quantity is None:
        return None
    format_factor = _format_factor(size_format)
    if format_factor is None:
        return None

    amount = Decimal(str(quantity))
    if not amount.is_finite() or amount <= 0:
        return None
    _, factor = format_factor
    milli = int((amount * factor).quantize(_CENT, rounding=ROUND_HALF_UP))
    return milli if milli > 0 else None


def reference_unit_for(size_format: str | None) -> str | None:
    """Unidad de referencia normalizada (`kg`, `l`, `g`, `ml` o `unit`)."""
    if size_format is None:
        return None
    return _REFERENCE_UNITS.get(normalize_token(size_format))


def normalize_product(product: MercadonaProduct, *, category_id: int) -> NormalizedProduct:
    """Normaliza un producto de una subcategoría concreta."""
    external_id = product.id.strip()
    if not external_id or len(external_id) > 64:
        raise NormalizationError(f"Identificador de producto no válido: {product.id!r}")

    instructions = product.price_instructions
    is_pack = bool(instructions and instructions.is_pack)
    total_units = instructions.total_units if instructions else None
    if total_units is not None and total_units > 1:
        is_pack = True

    package_price: int | None = None
    reference_price: int | None = None
    reference_unit: str | None = None
    quantity_milli: int | None = None
    package_unit: str | None = None
    is_estimated = False
    approx_size = False
    selling_method: int | None = None

    if instructions is not None:
        try:
            package_price = parse_price_cents(instructions.unit_price)
        except NormalizationError as exc:
            raise NormalizationError(
                f"Producto {product.id} ({product.display_name}): {exc}"
            ) from exc

        reference_unit = reference_unit_for(instructions.reference_format)
        if reference_unit is not None:
            try:
                reference_price = parse_price_cents(
                    instructions.reference_price or instructions.bulk_price
                )
            except NormalizationError:
                reference_price = None

        quantity = instructions.unit_size
        if quantity is None and is_pack and instructions.pack_size and total_units:
            quantity = instructions.pack_size * total_units
            is_estimated = True
        quantity_milli = quantity_to_milli(quantity, instructions.size_format)
        format_factor = _format_factor(instructions.size_format)
        if quantity_milli is not None and format_factor is not None:
            package_unit = format_factor[0]

        approx_size = bool(instructions.approx_size)
        selling_method = instructions.selling_method

    return NormalizedProduct(
        external_id=external_id,
        name=(" ".join(product.display_name.split()) or external_id)[:300],
        ean=_clip(product.ean, 32),
        brand=_clip(product.brand, 120),
        category_id=category_id,
        packaging=_clip(product.packaging, 120),
        package_quantity_milli=quantity_milli,
        package_unit=package_unit,
        is_estimated=is_estimated,
        package_price_cents=package_price,
        reference_price_cents=reference_price,
        reference_unit=reference_unit,
        is_pack=is_pack,
        approx_size=approx_size,
        selling_method=selling_method,
        thumbnail_url=product.thumbnail,
        published=product.published,
        unavailable_from=_clip(product.unavailable_from, 64),
    )


def is_food_category(name: str, *, level: int, parent_is_food: bool = True) -> bool:
    """Heurística conservadora para marcar secciones y subcategorías no alimentarias.

    El mapeo real de ingredientes es explícito (F2.3); este flag evita ofrecer
    limpieza, higiene o mascotas como si fueran comida.
    """
    if not parent_is_food:
        return False
    normalized = normalize_token(name)
    if level == 0:
        return not any(token in normalized for token in _NON_FOOD_SECTION_TOKENS)
    return not any(token in normalized for token in _NON_FOOD_SUBCATEGORY_TOKENS)
