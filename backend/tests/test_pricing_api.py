"""API del preview de coste (F3.5 y F3.7).

El preview no persiste menús, no aplica filtros de alérgenos y comparte el plan
de compra canónico con la futura lista de la compra de F4.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.main import create_app
from tests.domain_fixtures import (
    make_dish,
    make_ingredient,
    make_mapping,
    make_product,
    make_profile,
)

LOCAL_HOST = "127.0.0.1:8000"


def _seed_pricing(factory: sessionmaker[Session]) -> dict[str, int]:
    with factory() as session:
        chicken = make_ingredient(
            session,
            "chicken",
            name="Pollo",
            category="meat",
            group="protein",
            serving_group="protein",
            protein_source="chicken",
        )
        rice = make_ingredient(session, "rice", name="Arroz", group="carb", serving_group="carb")
        oil = make_ingredient(
            session,
            "olive-oil",
            name="Aceite de oliva",
            category="pantry",
            group="fat",
            base_unit="ml",
            serving_group="none",
        )
        milk = make_ingredient(
            session,
            "milk",
            name="Leche",
            category="dairy",
            group="dairy",
            base_unit="ml",
            serving_group="protein",
            protein_source="dairy",
            allergens=["milk"],
        )
        eggs = make_ingredient(
            session,
            "eggs",
            name="Huevos",
            category="eggs",
            group="protein",
            base_unit="unit",
            serving_group="protein",
            protein_source="eggs",
            allergens=["eggs"],
        )
        truffle = make_ingredient(session, "truffle", name="Trufa", category="pantry")

        chicken_product = make_product(
            session,
            "CHICKEN-500",
            name="Pollo 500 g",
            package_quantity_milli=500_000,
            package_unit="g",
            package_price_cents=450,
        )
        rice_product = make_product(
            session,
            "RICE-1KG",
            name="Arroz 1 kg",
            package_quantity_milli=1_000_000,
            package_unit="g",
            package_price_cents=115,
        )
        oil_product = make_product(
            session,
            "OIL-1L",
            name="Aceite 1 L",
            package_quantity_milli=1_000_000,
            package_unit="ml",
            package_price_cents=200,
        )
        milk_product = make_product(
            session,
            "MILK-1L",
            name="Leche 1 L",
            package_quantity_milli=1_000_000,
            package_unit="ml",
            package_price_cents=95,
        )
        eggs_product = make_product(
            session,
            "EGGS-12",
            name="Huevos docena",
            package_quantity_milli=12_000,
            package_unit="unit",
            package_price_cents=240,
        )
        truffle_product = make_product(
            session,
            "TRUFFLE",
            name="Trufa",
            package_quantity_milli=10_000,
            package_unit="g",
            package_price_cents=100,
            published=False,
        )
        for ingredient, product in [
            (chicken, chicken_product),
            (rice, rice_product),
            (oil, oil_product),
            (milk, milk_product),
            (eggs, eggs_product),
            (truffle, truffle_product),
        ]:
            make_mapping(session, ingredient, product)

        chicken_rice = make_dish(
            session,
            "chicken-rice",
            name="Pollo con arroz",
            meal_types=["lunch", "dinner"],
            ingredients=[
                (chicken, 300_000),
                (rice, 160_000),
                (oil, 15_000),
            ],
        )
        rice_salad = make_dish(
            session,
            "rice-salad",
            name="Ensalada de arroz",
            meal_types=["dinner"],
            light=True,
            tags=["salad"],
            ingredients=[
                (rice, 60_000),
                (chicken, 100_000),
                (oil, 10_000),
            ],
        )
        milk_dessert = make_dish(
            session,
            "milk-dessert",
            name="Postre de leche",
            meal_types=["dinner"],
            ingredients=[
                (milk, 200_000),
                (rice, 60_000),
            ],
        )
        egg_dish = make_dish(
            session,
            "egg-dish",
            name="Huevos con aceite",
            meal_types=["dinner"],
            ingredients=[
                (eggs, 2_000),
                (oil, 5_000),
            ],
        )
        truffle_dish = make_dish(
            session,
            "truffle-dish",
            name="Plato con trufa",
            meal_types=["dinner"],
            ingredients=[(truffle, 10_000)],
        )
        make_profile(session, people=2)
        session.commit()
        return {
            "chicken": chicken.id,
            "rice": rice.id,
            "oil": oil.id,
            "chicken_rice": chicken_rice.id,
            "rice_salad": rice_salad.id,
            "milk_dessert": milk_dessert.id,
            "egg_dish": egg_dish.id,
            "truffle_dish": truffle_dish.id,
        }


@pytest.fixture
def pricing_client(
    catalog_settings: Settings,
    catalog_session_factory: sessionmaker[Session],
) -> Iterator[TestClient]:
    _seed_pricing(catalog_session_factory)
    app = create_app(catalog_settings, session_factory=catalog_session_factory)
    with TestClient(app) as client:
        yield client


def _post(client: TestClient, url: str, body: dict[str, object]) -> object:
    return client.post(url, headers={"Host": LOCAL_HOST}, json=body)


def _preview(
    client: TestClient,
    dish_id: int,
    *,
    people: int = 2,
    pantry: list[dict[str, int]] | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {"people": people, "dishes": [{"dish_id": dish_id}]}
    if pantry is not None:
        body["pantry"] = pantry
    response = _post(client, "/api/pricing/preview", body)
    assert response.status_code == 200, response.text
    return response.json()


def test_preview_prices_single_dish(pricing_client: TestClient) -> None:
    ids = _seed_pricing_ids(pricing_client)
    payload = _preview(pricing_client, ids["chicken_rice"])

    assert payload["people"] == 2
    assert payload["dish_count"] == 1
    assert payload["ticket_cents"] == 765
    assert payload["consumption_cents"] == 291
    assert payload["pantry_consumption_cents"] == 0
    assert payload["leftover_value_cents"] == 474
    assert payload["dishes"][0]["consumption_cents"] == 291
    assert payload["dishes"][0]["per_serving_cents"] == 146

    ingredients = {item["ingredient"]["slug"]: item for item in payload["ingredients"]}
    assert ingredients["chicken"]["need_milli"] == 300_000
    assert ingredients["chicken"]["ticket_cents"] == 450
    assert ingredients["chicken"]["consumption_cents"] == 270
    assert ingredients["rice"]["consumption_cents"] == 18
    assert ingredients["olive-oil"]["consumption_cents"] == 3

    lines = [line for item in payload["ingredients"] for line in item["products"]]
    assert sum(line["subtotal_cents"] for line in lines) == payload["ticket_cents"]
    assert sum(item["ticket_cents"] for item in payload["ingredients"]) == payload["ticket_cents"]
    assert payload["ticket_cents"] + payload["pantry_consumption_cents"] == (
        payload["consumption_cents"] + payload["leftover_value_cents"]
    )


def test_preview_aggregates_repeated_dishes(pricing_client: TestClient) -> None:
    ids = _seed_pricing_ids(pricing_client)
    response = _post(
        pricing_client,
        "/api/pricing/preview",
        {
            "people": 2,
            "dishes": [{"dish_id": ids["chicken_rice"]}, {"dish_id": ids["chicken_rice"]}],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["dish_count"] == 2
    assert payload["ticket_cents"] == 1_215
    assert payload["consumption_cents"] == 583
    assert payload["leftover_value_cents"] == 632
    assert sum(dish["consumption_cents"] for dish in payload["dishes"]) == 583
    assert payload["ticket_cents"] + payload["pantry_consumption_cents"] == (
        payload["consumption_cents"] + payload["leftover_value_cents"]
    )


def test_preview_two_dishes_matches_sum_of_entries(pricing_client: TestClient) -> None:
    ids = _seed_pricing_ids(pricing_client)
    response = _post(
        pricing_client,
        "/api/pricing/preview",
        {
            "people": 2,
            "dishes": [{"dish_id": ids["chicken_rice"]}, {"dish_id": ids["rice_salad"]}],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["ticket_cents"] == 765
    assert payload["consumption_cents"] == 390
    assert payload["leftover_value_cents"] == 375
    assert [dish["consumption_cents"] for dish in payload["dishes"]] == [291, 99]
    assert (
        sum(dish["consumption_cents"] for dish in payload["dishes"]) == payload["consumption_cents"]
    )


def test_preview_uses_profile_pantry_and_allows_override(pricing_client: TestClient) -> None:
    ids = _seed_pricing_ids(pricing_client)
    update = pricing_client.put(
        "/api/pantry",
        headers={"Host": LOCAL_HOST},
        json={"items": [{"ingredient_id": ids["chicken"], "quantity_milli": 100_000}]},
    )
    assert update.status_code == 200

    with_profile = _preview(pricing_client, ids["chicken_rice"])
    assert with_profile["ticket_cents"] == 765
    assert with_profile["consumption_cents"] == 291
    assert with_profile["pantry_consumption_cents"] == 90
    assert with_profile["leftover_value_cents"] == 564

    without_pantry = _preview(pricing_client, ids["chicken_rice"], pantry=[])
    assert without_pantry["pantry_consumption_cents"] == 0
    assert without_pantry["leftover_value_cents"] == 474

    fully_covered = _preview(
        pricing_client,
        ids["chicken_rice"],
        pantry=[{"ingredient_id": ids["chicken"], "quantity_milli": 300_000}],
    )
    assert fully_covered["ticket_cents"] == 315
    assert fully_covered["consumption_cents"] == 291
    assert fully_covered["pantry_consumption_cents"] == 270
    assert fully_covered["leftover_value_cents"] == 294
    assert fully_covered["ticket_cents"] + fully_covered["pantry_consumption_cents"] == (
        fully_covered["consumption_cents"] + fully_covered["leftover_value_cents"]
    )


def test_preview_prices_eggs_in_units(pricing_client: TestClient) -> None:
    ids = _seed_pricing_ids(pricing_client)
    payload = _preview(pricing_client, ids["egg_dish"])

    eggs = next(item for item in payload["ingredients"] if item["ingredient"]["slug"] == "eggs")
    assert eggs["need_milli"] == 2_000
    assert eggs["products"][0]["package_quantity_milli"] == 12_000
    assert eggs["products"][0]["packages"] == 1
    assert payload["ticket_cents"] == 440
    assert payload["consumption_cents"] == 41
    assert payload["leftover_value_cents"] == 399


def test_preview_ignores_allergens(pricing_client: TestClient) -> None:
    ids = _seed_pricing_ids(pricing_client)
    update = pricing_client.put(
        "/api/profile",
        headers={"Host": LOCAL_HOST},
        json={"people": 2, "days": 7, "budget_cents": 7000, "allergen_codes": ["milk"]},
    )
    assert update.status_code == 200

    payload = _preview(pricing_client, ids["milk_dessert"])
    assert payload["consumption_cents"] == 26
    assert payload["ticket_cents"] == 210


def test_preview_does_not_persist_menus(pricing_client: TestClient) -> None:
    ids = _seed_pricing_ids(pricing_client)
    before = _table_counts(pricing_client)
    first = _preview(pricing_client, ids["chicken_rice"])
    second = _preview(pricing_client, ids["chicken_rice"])
    after = _table_counts(pricing_client)

    assert first == second
    assert before == after
    assert "menus" not in after or after["menus"] == 0


def test_preview_rejects_missing_dish(pricing_client: TestClient) -> None:
    response = _post(
        pricing_client,
        "/api/pricing/preview",
        {"people": 2, "dishes": [{"dish_id": 99999}]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["error"]["details"]["dish_ids"] == [99999]


def test_preview_validates_people_and_dishes(pricing_client: TestClient) -> None:
    ids = _seed_pricing_ids(pricing_client)
    for people in (0, 11):
        response = _post(
            pricing_client,
            "/api/pricing/preview",
            {"people": people, "dishes": [{"dish_id": ids["chicken_rice"]}]},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    empty = _post(pricing_client, "/api/pricing/preview", {"people": 2, "dishes": []})
    assert empty.status_code == 422

    duplicate_pantry = _post(
        pricing_client,
        "/api/pricing/preview",
        {
            "people": 2,
            "dishes": [{"dish_id": ids["chicken_rice"]}],
            "pantry": [
                {"ingredient_id": ids["chicken"], "quantity_milli": 1000},
                {"ingredient_id": ids["chicken"], "quantity_milli": 2000},
            ],
        },
    )
    assert duplicate_pantry.status_code == 422


def test_preview_rejects_unknown_pantry_ingredient(pricing_client: TestClient) -> None:
    ids = _seed_pricing_ids(pricing_client)
    response = _post(
        pricing_client,
        "/api/pricing/preview",
        {
            "people": 2,
            "dishes": [{"dish_id": ids["chicken_rice"]}],
            "pantry": [{"ingredient_id": 99999, "quantity_milli": 1000}],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"]["ingredient_ids"] == [99999]


def test_preview_product_unavailable(pricing_client: TestClient) -> None:
    ids = _seed_pricing_ids(pricing_client)
    response = _post(
        pricing_client,
        "/api/pricing/preview",
        {"people": 2, "dishes": [{"dish_id": ids["truffle_dish"]}]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRODUCT_UNAVAILABLE"
    assert response.json()["error"]["details"]["ingredient_name"] == "Trufa"


def _seed_pricing_ids(client: TestClient) -> dict[str, int]:
    dishes = _get(client, "/api/dishes").json()["items"]
    by_slug = {dish["slug"]: dish["id"] for dish in dishes}
    ingredients = _get(client, "/api/ingredients").json()["items"]
    by_ingredient = {ingredient["slug"]: ingredient["id"] for ingredient in ingredients}
    return {
        "chicken_rice": by_slug["chicken-rice"],
        "rice_salad": by_slug["rice-salad"],
        "milk_dessert": by_slug["milk-dessert"],
        "egg_dish": by_slug["egg-dish"],
        "truffle_dish": by_slug["truffle-dish"],
        "chicken": by_ingredient["chicken"],
        "rice": by_ingredient["rice"],
    }


def _get(client: TestClient, url: str) -> object:
    return client.get(url, headers={"Host": LOCAL_HOST})


def _table_counts(client: TestClient) -> dict[str, int]:
    factory: sessionmaker[Session] = client.app.state.session_factory
    with factory() as session:
        tables = inspect(session.get_bind()).get_table_names()
        return {
            table: int(session.scalar(text(f'SELECT COUNT(*) FROM "{table}"')) or 0)
            for table in tables
        }
