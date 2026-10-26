"""Lista canónica de alérgenos del MVP.

Los códigos son estables y en inglés; la UI se encarga de traducirlos. `unknown`
representa un producto cuyo detalle no permite confirmar la ausencia de alérgenos
y se trata de forma fail-closed cuando el usuario declara alérgenos.
"""

from enum import StrEnum


class AllergenCode(StrEnum):
    """Códigos admitidos por el modelo de datos."""

    gluten = "gluten"
    crustaceans = "crustaceans"
    eggs = "eggs"
    fish = "fish"
    peanuts = "peanuts"
    soybeans = "soybeans"
    milk = "milk"
    nuts = "nuts"
    celery = "celery"
    mustard = "mustard"
    sesame = "sesame"
    sulphites = "sulphites"
    lupin = "lupin"
    molluscs = "molluscs"
    unknown = "unknown"


#: Orden canónico usado por la API y los tests.
ALLERGEN_CODES: tuple[str, ...] = tuple(code.value for code in AllergenCode)
ALLERGEN_CODE_SET: frozenset[str] = frozenset(ALLERGEN_CODES)

#: Nombres para la UI; el dominio y la API usan los códigos en inglés.
ALLERGEN_LABELS: dict[str, str] = {
    "gluten": "Gluten",
    "crustaceans": "Crustáceos",
    "eggs": "Huevo",
    "fish": "Pescado",
    "peanuts": "Cacahuetes",
    "soybeans": "Soja",
    "milk": "Leche",
    "nuts": "Frutos de cáscara",
    "celery": "Apio",
    "mustard": "Mostaza",
    "sesame": "Sésamo",
    "sulphites": "Sulfitos",
    "lupin": "Altramuces",
    "molluscs": "Moluscos",
    "unknown": "Sin confirmar",
}
