"""Enriquecimiento de alérgenos de productos mapeados (F2.4).

Solo se descarga el detalle de los productos que pertenecen a algún ingrediente
canónico. La política es fail-closed:

- `known`: hay una declaración de alérgenos y/o los ingredientes permiten
  confirmar la ausencia de los códigos conocidos.
- `partial`: la declaración y los ingredientes no coinciden, o solo hay datos
  parciales. Se excluye cuando el usuario declara alérgenos.
- `unknown`: no hay datos suficientes. También se excluye con alérgenos.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.allergens import ALLERGEN_CODES
from app.models.catalog import Product, ProductAllergen
from app.models.ingredients import IngredientProduct
from app.schemas.mercadona import MercadonaProductDetail
from app.services.mercadona_client import MercadonaClient

logger = logging.getLogger(__name__)

MAX_CONCURRENCY = 4

_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
_X99 = re.compile(r"\bx99\b", re.IGNORECASE)

#: Términos que identifican cada alérgeno en el texto de Mercadona. Se comparan
#: sin acentos y en minúsculas. Se evitan términos genéricos que producen falsos
#: positivos claros (por ejemplo, «nuez moscada» no es un fruto de cáscara).
ALLERGEN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "gluten": ("gluten", "trigo", "cebada", "centeno", "avena", "espelta", "kamut", "malta"),
    "crustaceans": (
        "crustaceo",
        "gamba",
        "langostino",
        "cangrejo",
        "langosta",
        "bogavante",
        "camaron",
    ),
    "eggs": ("huevo", "clara de huevo", "yema de huevo", "ovoalbumina"),
    "fish": (
        "pescado",
        "salmon",
        "merluza",
        "atun",
        "sardina",
        "caballa",
        "anchoa",
        "bacalao",
        "lubina",
        "dorada",
        "trucha",
        "boqueron",
        "melva",
        "arenque",
        "panga",
    ),
    "peanuts": ("cacahuete", "cacahuate"),
    "soybeans": ("soja", "soya"),
    "milk": (
        "leche",
        "lactosa",
        "lacteo",
        "queso",
        "yogur",
        "nata",
        "mantequilla",
        "suero",
        "caseina",
        "caseinato",
    ),
    "nuts": (
        "frutos de cascara",
        "almendra",
        "avellana",
        "pistacho",
        "anacardo",
        "castana",
        "macadamia",
        "pecana",
        "nueces",
    ),
    "celery": ("apio",),
    "mustard": ("mostaza",),
    "sesame": ("sesamo", "tahini"),
    "sulphites": ("sulfito", "disulfito", "metabisulfito"),
    "lupin": ("altramuz", "lupino", "lupin"),
    "molluscs": (
        "molusco",
        "mejillon",
        "almeja",
        "calamar",
        "pulpo",
        "sepia",
        "vieira",
        "ostra",
    ),
}


class ProductDetailClient(Protocol):
    """Contrato mínimo del cliente de detalle (permite dobles en tests)."""

    async def get_product(self, product_id: str) -> MercadonaProductDetail: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ExtractedAllergen:
    """Alérgeno detectado, con su origen y confianza."""

    code: str
    source: str
    confidence: str


@dataclass(frozen=True, slots=True)
class AllergenExtraction:
    """Resultado de interpretar la información de alérgenos de un producto."""

    status: str
    allergens: tuple[ExtractedAllergen, ...] = ()


@dataclass(slots=True)
class AllergenSyncResult:
    """Resumen del enriquecimiento de productos mapeados."""

    products_seen: int = 0
    updated: int = 0
    unknown: int = 0
    partial: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)


def _plain_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(_HTML_TAG.sub(" ", value))
    text = _X99.sub(" ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return _WHITESPACE.sub(" ", text).strip()


def _find_codes(text: str) -> set[str]:
    normalized = text.lower()
    found: set[str] = set()
    for code, keywords in ALLERGEN_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            found.add(code)
    return found


def parse_allergen_info(
    allergens_html: str | None, ingredients_html: str | None
) -> AllergenExtraction:
    """Interpreta el HTML de alérgenos e ingredientes de Mercadona.

    `x99` es el centinela de «sin declaración explícita». Se combina con una
    búsqueda de alérgenos en la lista de ingredientes para no dar por bueno un
    producto que menciona un alérgeno en su composición.
    """
    allergens_text = _plain_text(allergens_html)
    ingredients_text = _plain_text(ingredients_html)
    declared = _find_codes(allergens_text)
    from_ingredients = _find_codes(ingredients_text)
    has_declaration = bool(re.search(r"[a-z0-9]", allergens_text, re.IGNORECASE))

    if has_declaration:
        extra = from_ingredients - declared
        status = "partial" if extra else "known"
        extracted = [ExtractedAllergen(code, "api", "high") for code in sorted(declared)]
        extracted.extend(ExtractedAllergen(code, "ingredients", "medium") for code in sorted(extra))
        if not declared and not extra:
            lowered = allergens_text.lower()
            if "sin alergeno" in lowered or "no contiene" in lowered:
                status = "known"
            elif "contiene" in lowered or "puede contener" in lowered:
                status = "partial"
        return AllergenExtraction(status=status, allergens=tuple(extracted))

    if not ingredients_text:
        return AllergenExtraction(status="unknown")

    if from_ingredients:
        return AllergenExtraction(
            status="partial",
            allergens=tuple(
                ExtractedAllergen(code, "ingredients", "medium")
                for code in sorted(from_ingredients)
            ),
        )
    return AllergenExtraction(status="known")


class AllergenSyncService:
    """Descarga el detalle de los productos mapeados y actualiza sus alérgenos."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        client_factory: Callable[[], ProductDetailClient] | None = None,
        max_concurrency: int = MAX_CONCURRENCY,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency debe ser mayor que cero")
        self._session_factory = session_factory
        self._client_factory = client_factory or MercadonaClient
        self._max_concurrency = max_concurrency

    async def run(self) -> AllergenSyncResult:
        """Enriquece todos los productos mapeados; no falla si uno no responde."""
        with self._session_factory() as session:
            rows = session.execute(
                select(Product.id, Product.external_id)
                .join(IngredientProduct, IngredientProduct.product_id == Product.id)
                .distinct()
                .order_by(Product.id)
            ).all()
        result = AllergenSyncResult(products_seen=len(rows))
        if not rows:
            return result

        client = self._client_factory()
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def fetch(
            internal_id: int, external_id: str
        ) -> tuple[int, str, MercadonaProductDetail | None, Exception | None]:
            async with semaphore:
                try:
                    detail = await client.get_product(external_id)
                except Exception as exc:  # noqa: BLE001 - se registra por producto
                    return internal_id, external_id, None, exc
                return internal_id, external_id, detail, None

        try:
            responses = await asyncio.gather(
                *(fetch(internal_id, external_id) for internal_id, external_id in rows)
            )
        finally:
            try:
                await client.close()
            except Exception:  # noqa: BLE001 - cerrar no oculta el resultado
                logger.debug("Error cerrando el cliente de detalle", exc_info=True)

        extractions: list[tuple[int, AllergenExtraction]] = []
        for internal_id, external_id, detail, failure in responses:
            if failure is not None or detail is None:
                message = str(failure) if failure is not None else "Sin detalle"
                result.failed.append((external_id, message[:300]))
                continue
            nutrition = detail.nutrition_information
            extraction = parse_allergen_info(
                nutrition.allergens if nutrition else None,
                nutrition.ingredients if nutrition else None,
            )
            extractions.append((internal_id, extraction))
            if extraction.status == "unknown":
                result.unknown += 1
            elif extraction.status == "partial":
                result.partial += 1

        if extractions:
            with self._session_factory() as session:
                for internal_id, extraction in extractions:
                    product = session.get(Product, internal_id)
                    if product is None:
                        continue
                    product.allergen_status = extraction.status
                    session.execute(
                        delete(ProductAllergen).where(ProductAllergen.product_id == internal_id)
                    )
                    for allergen in extraction.allergens:
                        if allergen.code not in ALLERGEN_CODES:
                            continue
                        session.add(
                            ProductAllergen(
                                product_id=internal_id,
                                allergen_code=allergen.code,
                                source=allergen.source,
                                confidence=allergen.confidence,
                            )
                        )
                    result.updated += 1
                session.commit()

        if result.failed:
            logger.warning(
                "No se pudieron enriquecer %s productos de alérgenos", len(result.failed)
            )
        return result
