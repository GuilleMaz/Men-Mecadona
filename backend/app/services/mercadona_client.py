"""Cliente HTTP de solo lectura para la tienda online de Mercadona.

Fija el CP 22002 y exige que la API confirme el almacén 4389 antes de devolver
catálogo. No automatiza la compra ni maneja credenciales.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import EXPECTED_WAREHOUSE, POSTAL_CODE
from app.schemas.mercadona import (
    MercadonaCategoriesPage,
    MercadonaCategoryDetail,
    MercadonaSection,
)

MERCADONA_BASE_URL = "https://tienda.mercadona.es"
CHANGE_POSTAL_CODE_PATH = "/api/postal-codes/actions/change-pc/"
CATEGORIES_PATH = "/api/categories/"

#: Límite defensivo para no seguir paginaciones infinitas.
MAX_CATEGORY_PAGES = 25

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class MercadonaError(Exception):
    """Error de dominio del cliente, con código estable."""

    code = "MERCADONA_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class WarehouseUnavailableError(MercadonaError):
    """La API no confirmó el almacén esperado para el CP."""

    code = "WAREHOUSE_UNAVAILABLE"


class MercadonaUnavailableError(MercadonaError):
    """Mercadona no respondió tras agotar los reintentos."""

    code = "MERCADONA_UNAVAILABLE"


class MercadonaHTTPError(MercadonaError):
    """Mercadona respondió con un estado HTTP de error."""

    code = "MERCADONA_HTTP_ERROR"


class MercadonaResponseError(MercadonaError):
    """La respuesta no tiene el formato esperado."""

    code = "MERCADONA_INVALID_RESPONSE"


class _RetryableRequest(Exception):
    """Fallo transitorio que merece un reintento."""


class MercadonaClient:
    """Cliente asíncrono del catálogo de Mercadona.

    La primera petición fija el CP y valida el almacén; el resto reutiliza la
    sesión (cookies) del mismo `httpx.AsyncClient`.
    """

    def __init__(
        self,
        *,
        base_url: str = MERCADONA_BASE_URL,
        postal_code: str = POSTAL_CODE,
        expected_warehouse: str = EXPECTED_WAREHOUSE,
        timeout: float = 10.0,
        max_attempts: int = 3,
        retry_wait_seconds: float = 0.5,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._postal_code = postal_code
        self._expected_warehouse = expected_warehouse
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._retry_wait_seconds = retry_wait_seconds
        self._client: httpx.AsyncClient | None = None
        self._session_ready = False
        self._warehouse: str | None = None
        self._postal_code_header: str | None = None

    @property
    def warehouse(self) -> str | None:
        """Almacén confirmado por la API, si la sesión ya arrancó."""
        return self._warehouse

    @property
    def postal_code_header(self) -> str | None:
        """CP devuelto por la API, si la sesión ya arrancó."""
        return self._postal_code_header

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Cierra la conexión y olvida la sesión."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._session_ready = False
        self._warehouse = None
        self._postal_code_header = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Cesta/0.1 (uso personal local)",
                },
            )
        return self._client

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Ejecuta una petición con reintentos ante fallos transitorios."""
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_attempts),
                wait=wait_exponential(
                    multiplier=self._retry_wait_seconds,
                    min=self._retry_wait_seconds,
                ),
                retry=retry_if_exception_type(_RetryableRequest),
                reraise=True,
            ):
                with attempt:
                    try:
                        response = await self._http().request(method, url, **kwargs)
                    except httpx.TransportError as exc:
                        raise _RetryableRequest(str(exc)) from exc
                    if response.status_code == 429 or response.status_code >= 500:
                        raise _RetryableRequest(f"HTTP {response.status_code} en {url}")
                    if response.status_code >= 400:
                        raise MercadonaHTTPError(
                            f"Mercadona respondió {response.status_code} en {url}."
                        )
                    return response
        except _RetryableRequest as exc:
            raise MercadonaUnavailableError(
                "Mercadona no responde tras varios intentos. Inténtalo más tarde."
            ) from exc
        raise AssertionError("bucle de reintentos sin resultado")  # pragma: no cover

    async def _ensure_session(self) -> None:
        """Fija el CP y valida el almacén una sola vez por sesión."""
        if self._session_ready:
            return

        response = await self._request(
            "PUT",
            CHANGE_POSTAL_CODE_PATH,
            json={"new_postal_code": self._postal_code},
        )
        warehouse = response.headers.get("x-customer-wh")
        if warehouse != self._expected_warehouse:
            raise WarehouseUnavailableError(
                "No se pudo confirmar el almacén "
                f"{self._expected_warehouse} para el CP {self._postal_code}."
            )

        self._warehouse = warehouse
        self._postal_code_header = response.headers.get("x-customer-pc")
        self._session_ready = True

    @staticmethod
    def _with_warehouse(url: str, warehouse: str) -> str:
        """Añade `wh` a la URL conservando los parámetros de paginación."""
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        query["wh"] = warehouse
        return urlunsplit(parts._replace(query=urlencode(query)))

    @staticmethod
    def _parse(model: type[_ModelT], response: httpx.Response) -> _ModelT:
        try:
            return model.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise MercadonaResponseError(
                "Mercadona devolvió una respuesta con un formato inesperado."
            ) from exc

    async def get_sections(self) -> list[MercadonaSection]:
        """Descarga el árbol de secciones y subcategorías, siguiendo paginación."""
        await self._ensure_session()

        sections: list[MercadonaSection] = []
        url: str | None = CATEGORIES_PATH
        page_count = 0
        while url is not None:
            page_count += 1
            if page_count > MAX_CATEGORY_PAGES:
                raise MercadonaResponseError("Mercadona devolvió demasiadas páginas de categorías.")
            response = await self._request(
                "GET",
                self._with_warehouse(url, self._expected_warehouse),
            )
            page = self._parse(MercadonaCategoriesPage, response)
            sections.extend(page.results)
            url = page.next

        return sections

    async def get_subcategory(self, subcategory_id: int) -> MercadonaCategoryDetail:
        """Descarga una subcategoría con sus grupos y productos."""
        await self._ensure_session()
        response = await self._request(
            "GET",
            f"/api/categories/{subcategory_id}/",
            params={"wh": self._expected_warehouse},
        )
        return self._parse(MercadonaCategoryDetail, response)
