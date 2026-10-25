"""Cliente de Mercadona con respx y fixtures sintéticas, sin red."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from app.schemas.mercadona import MercadonaProduct
from app.services.mercadona_client import (
    CHANGE_POSTAL_CODE_PATH,
    MERCADONA_BASE_URL,
    MercadonaClient,
    MercadonaHTTPError,
    MercadonaResponseError,
    MercadonaUnavailableError,
    WarehouseUnavailableError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mercadona"
CHANGE_POSTAL_CODE_URL = f"{MERCADONA_BASE_URL}{CHANGE_POSTAL_CODE_PATH}"
CATEGORIES_URL = f"{MERCADONA_BASE_URL}/api/categories/"
SUBCATEGORY_112_URL = f"{MERCADONA_BASE_URL}/api/categories/112/"
EXPECTED_HEADERS = {"x-customer-wh": "4389", "x-customer-pc": "22002"}


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def mock_postal_code(headers: dict[str, str] | None = None) -> respx.Route:
    return respx.put(CHANGE_POSTAL_CODE_URL).mock(
        return_value=httpx.Response(
            200,
            headers=EXPECTED_HEADERS if headers is None else headers,
            json={"warehouse_changed": False},
        )
    )


def mock_categories() -> respx.Route:
    return respx.get(CATEGORIES_URL).mock(
        return_value=httpx.Response(200, json=load_fixture("categories.json"))
    )


def mock_subcategory_112() -> respx.Route:
    return respx.get(SUBCATEGORY_112_URL).mock(
        return_value=httpx.Response(200, json=load_fixture("subcategory_112.json"))
    )


def test_product_accepts_fractional_pack_size() -> None:
    product = MercadonaProduct.model_validate(
        {
            "id": 9004,
            "display_name": "Agua mineral 1,5 L (pack 6)",
            "price_instructions": {
                "is_pack": True,
                "pack_size": 1.5,
                "total_units": 6,
                "unit_size": 9.0,
                "size_format": "l",
                "unit_price": "1.62",
                "bulk_price": "0.18",
            },
        }
    )

    assert product.price_instructions is not None
    assert product.id == "9004"
    assert product.price_instructions.pack_size == 1.5
    assert product.price_instructions.total_units == 6
    assert product.price_instructions.unit_size == 9.0


def test_product_accepts_variable_weight_variant_id() -> None:
    product = MercadonaProduct.model_validate(
        {
            "id": "81649.1",
            "display_name": "Salmón a rodajas",
            "price_instructions": {
                "unit_size": 2.991,
                "size_format": "kg",
                "unit_price": "32.75",
                "bulk_price": "10.95",
                "approx_size": True,
            },
        }
    )

    assert product.id == "81649.1"
    assert product.price_instructions is not None
    assert product.price_instructions.approx_size is True
    assert product.price_instructions.size_format == "kg"


async def test_full_flow_parses_sections_and_products() -> None:
    with respx.mock:
        put_route = mock_postal_code()
        categories_route = mock_categories()
        subcategory_route = mock_subcategory_112()

        async with MercadonaClient(retry_wait_seconds=0) as client:
            sections = await client.get_sections()
            detail = await client.get_subcategory(112)

            assert client.warehouse == "4389"
            assert client.postal_code_header == "22002"

        assert put_route.call_count == 1

    assert len(sections) == 1
    assert sections[0].name == "Aceite, especias y salsas"
    assert [subcategory.id for subcategory in sections[0].categories] == [112, 113]

    products = detail.all_products()
    assert [product.id for product in products] == ["9001", "9003", "9002"]

    oil = products[0]
    assert oil.display_name == "Aceite de oliva sintético 5 L"
    assert oil.price_instructions is not None
    assert oil.price_instructions.unit_price == "17.25"
    assert oil.price_instructions.unit_size == 5.0
    assert oil.price_instructions.size_format == "l"

    pack = products[1]
    assert pack.price_instructions is not None
    assert pack.price_instructions.is_pack is True
    assert pack.price_instructions.pack_size == 6
    assert pack.price_instructions.total_units == 6

    put_body = json.loads(put_route.calls[0].request.content)
    assert put_body == {"new_postal_code": "22002"}
    assert categories_route.calls[0].request.url.params["wh"] == "4389"
    assert subcategory_route.calls[0].request.url.params["wh"] == "4389"


async def test_follows_categories_pagination() -> None:
    first_section = load_fixture("categories.json")["results"][0]
    second_section = {**first_section, "id": 99, "name": "Bebidas"}
    second_page_url = f"{CATEGORIES_URL}?page=2"

    first_page = {
        "count": 2,
        "next": second_page_url,
        "previous": None,
        "results": [first_section],
    }
    second_page = {
        "count": 2,
        "next": None,
        "previous": None,
        "results": [second_section],
    }

    def page_handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=second_page)
        return httpx.Response(200, json=first_page)

    with respx.mock:
        mock_postal_code()
        route = respx.get(CATEGORIES_URL).mock(side_effect=page_handler)

        async with MercadonaClient(retry_wait_seconds=0) as client:
            sections = await client.get_sections()

    assert [section.id for section in sections] == [12, 99]
    assert route.call_count == 2
    assert route.calls[0].request.url.params["wh"] == "4389"
    assert route.calls[1].request.url.params["page"] == "2"
    assert route.calls[1].request.url.params["wh"] == "4389"


async def test_session_is_initialized_once_under_concurrency() -> None:
    def subcategory_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=load_fixture("subcategory_112.json"))

    with respx.mock:
        put_route = mock_postal_code()
        respx.get(SUBCATEGORY_112_URL).mock(side_effect=subcategory_handler)

        async with MercadonaClient(retry_wait_seconds=0) as client:
            details = await asyncio.gather(*(client.get_subcategory(112) for _ in range(4)))

    assert put_route.call_count == 1
    assert all(len(detail.all_products()) == 3 for detail in details)


async def test_warehouse_mismatch_blocks_catalog_download() -> None:
    with respx.mock:
        mock_postal_code({"x-customer-wh": "9999", "x-customer-pc": "22002"})
        categories_route = mock_categories()
        client = MercadonaClient(retry_wait_seconds=0)

        with pytest.raises(WarehouseUnavailableError) as error:
            await client.get_sections()
        await client.close()

    assert error.value.code == "WAREHOUSE_UNAVAILABLE"
    assert not categories_route.called


async def test_missing_warehouse_header_is_rejected() -> None:
    with respx.mock:
        mock_postal_code({"x-customer-pc": "22002"})
        client = MercadonaClient(retry_wait_seconds=0)

        with pytest.raises(WarehouseUnavailableError):
            await client.get_sections()
        await client.close()


async def test_retries_transient_server_errors() -> None:
    with respx.mock:
        mock_postal_code()
        route = respx.get(CATEGORIES_URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json=load_fixture("categories.json")),
            ]
        )

        async with MercadonaClient(retry_wait_seconds=0) as client:
            sections = await client.get_sections()

    assert len(sections) == 1
    assert route.call_count == 2


async def test_retries_transient_forbidden_rate_limit() -> None:
    with respx.mock:
        mock_postal_code()
        route = respx.get(CATEGORIES_URL).mock(
            side_effect=[
                httpx.Response(403),
                httpx.Response(200, json=load_fixture("categories.json")),
            ]
        )

        async with MercadonaClient(retry_wait_seconds=0) as client:
            sections = await client.get_sections()

    assert len(sections) == 1
    assert route.call_count == 2


async def test_exhausted_retries_raise_unavailable() -> None:
    with respx.mock:
        mock_postal_code()
        route = respx.get(CATEGORIES_URL).mock(
            side_effect=[httpx.Response(503), httpx.Response(503)]
        )

        async with MercadonaClient(retry_wait_seconds=0, max_attempts=2) as client:
            with pytest.raises(MercadonaUnavailableError) as error:
                await client.get_sections()

    assert error.value.code == "MERCADONA_UNAVAILABLE"
    assert route.call_count == 2


async def test_http_error_is_reported_with_stable_code() -> None:
    with respx.mock:
        mock_postal_code()
        respx.get(SUBCATEGORY_112_URL).mock(
            return_value=httpx.Response(404, json={"errors": [{"code": "not_found"}]})
        )

        async with MercadonaClient(retry_wait_seconds=0) as client:
            with pytest.raises(MercadonaHTTPError) as error:
                await client.get_subcategory(112)

    assert error.value.code == "MERCADONA_HTTP_ERROR"
    assert "404" in str(error.value)


async def test_invalid_response_shape_is_reported() -> None:
    with respx.mock:
        mock_postal_code()
        respx.get(CATEGORIES_URL).mock(
            return_value=httpx.Response(
                200,
                json={"count": 1, "next": None, "previous": None, "results": "no-es-lista"},
            )
        )

        async with MercadonaClient(retry_wait_seconds=0) as client:
            with pytest.raises(MercadonaResponseError) as error:
                await client.get_sections()

    assert error.value.code == "MERCADONA_INVALID_RESPONSE"
