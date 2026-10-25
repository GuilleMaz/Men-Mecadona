"""DTOs de la API pública de Mercadona.

Solo modelan los campos que necesita Cesta. `extra="ignore"` desacopla el cliente de
detalles cambiantes de la API y no se persiste el JSON original (`raw_json`).
Los precios se conservan como texto: la normalización a céntimos es responsabilidad
de F1.3.
"""

from pydantic import BaseModel, ConfigDict, Field


class _MercadonaModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class MercadonaSubcategory(_MercadonaModel):
    """Subcategoría tal y como aparece en el árbol de secciones."""

    id: int
    name: str


class MercadonaSection(_MercadonaModel):
    """Sección de primer nivel (`/api/categories/`)."""

    id: int
    name: str
    categories: list[MercadonaSubcategory] = Field(default_factory=list)


class MercadonaCategoriesPage(_MercadonaModel):
    """Sobre paginado del árbol de categorías."""

    count: int
    next: str | None = None
    previous: str | None = None
    results: list[MercadonaSection] = Field(default_factory=list)


class MercadonaPriceInstructions(_MercadonaModel):
    """Instrucciones de precio y formato de un producto."""

    unit_price: str | None = None
    bulk_price: str | None = None
    reference_price: str | None = None
    reference_format: str | None = None
    unit_size: float | None = None
    size_format: str | None = None
    is_pack: bool | None = None
    #: Tamaño de cada unidad del pack (puede ser decimal: 6 x 1,5 L -> 1.5).
    pack_size: float | None = None
    total_units: int | None = None
    approx_size: bool | None = None
    selling_method: int | None = None
    unit_name: str | None = None
    unit_selector: bool | None = None
    bunch_selector: bool | None = None
    drained_weight: float | None = None
    tax_percentage: str | None = None
    price_decreased: bool | None = None
    previous_unit_price: str | None = None
    min_bunch_amount: float | None = None
    increment_bunch_amount: float | None = None


class MercadonaProductCategory(_MercadonaModel):
    """Categoría interna a la que pertenece un producto."""

    id: int
    name: str


class MercadonaProduct(_MercadonaModel):
    """Producto de una subcategoría."""

    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)

    #: Identificador externo. Puede ser numérico o con sufijo de variante ("81649.1").
    id: str
    display_name: str
    slug: str | None = None
    published: bool = True
    status: str | None = None
    packaging: str | None = None
    thumbnail: str | None = None
    limit: int | None = None
    unavailable_from: str | None = None
    price_instructions: MercadonaPriceInstructions | None = None
    categories: list[MercadonaProductCategory] = Field(default_factory=list)


class MercadonaProductGroup(_MercadonaModel):
    """Grupo hijo de una subcategoría; contiene los productos."""

    id: int
    name: str
    products: list[MercadonaProduct] = Field(default_factory=list)


class MercadonaCategoryDetail(_MercadonaModel):
    """Detalle de una subcategoría con sus grupos y productos."""

    id: int
    name: str
    products: list[MercadonaProduct] = Field(default_factory=list)
    categories: list[MercadonaProductGroup] = Field(default_factory=list)

    def all_products(self) -> list[MercadonaProduct]:
        """Productos directos y de los grupos hijos, en el orden de la API."""
        products = list(self.products)
        for group in self.categories:
            products.extend(group.products)
        return products
