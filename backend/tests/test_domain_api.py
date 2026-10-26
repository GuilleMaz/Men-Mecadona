"""API de platos, ingredientes, perfil, exclusiones y despensa (F2.8)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.main import create_app
from app.models.catalog import ProductAllergen
from tests.domain_fixtures import (
    make_dish,
    make_ingredient,
    make_mapping,
    make_product,
    make_profile,
)

LOCAL_HOST = "127.0.0.1:8000"


def _seed_domain(factory: sessionmaker[Session]) -> dict[str, int]:
    with factory() as session:
        rice = make_ingredient(session, "rice", name="Arroz", group="carb", serving_group="carb")
        chicken = make_ingredient(
            session,
            "chicken",
            name="Pollo",
            category="meat",
            group="protein",
            serving_group="protein",
            protein_source="chicken",
        )
        onion = make_ingredient(session, "onion", name="Cebolla")
        tomato = make_ingredient(session, "tomato", name="Tomate")
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
        rice_product = make_product(session, "1001", name="Arroz", package_unit="g")
        chicken_product = make_product(session, "1002", name="Pollo", package_unit="g")
        onion_product = make_product(session, "1003", name="Cebolla", package_unit="g")
        tomato_product = make_product(session, "1004", name="Tomate", package_unit="g")
        milk_product = make_product(
            session, "1005", name="Leche", package_unit="ml", allergen_status="known"
        )
        for ingredient, product in [
            (rice, rice_product),
            (chicken, chicken_product),
            (onion, onion_product),
            (tomato, tomato_product),
            (milk, milk_product),
        ]:
            make_mapping(session, ingredient, product)
        session.add(
            ProductAllergen(
                product_id=milk_product.id,
                allergen_code="milk",
                source="test",
                confidence="high",
            )
        )
        chicken_rice = make_dish(
            session,
            "chicken-rice",
            name="Pollo con arroz",
            meal_types=["lunch", "dinner"],
            protein_sources=["chicken"],
            tags=["rice"],
            ingredients=[
                (chicken, 300_000),
                (rice, 160_000),
                (onion, 100_000),
                (tomato, 150_000),
            ],
        )
        rice_salad = make_dish(
            session,
            "rice-salad",
            name="Ensalada de arroz",
            meal_types=["dinner"],
            light=True,
            carbs="rice",
            tags=["salad"],
            ingredients=[
                (rice, 60_000),
                (tomato, 150_000),
                (onion, 100_000),
                (chicken, 100_000),
            ],
        )
        milk_dish = make_dish(
            session,
            "milk-dessert",
            name="Postre de leche",
            meal_types=["dinner"],
            carbs=None,
            tags=["dessert"],
            ingredients=[
                (milk, 200_000),
                (rice, 60_000),
                (tomato, 100_000),
                (onion, 50_000),
            ],
        )
        make_profile(session)
        session.commit()
        return {
            "rice": rice.id,
            "chicken": chicken.id,
            "onion": onion.id,
            "milk": milk.id,
            "chicken_rice": chicken_rice.id,
            "rice_salad": rice_salad.id,
            "milk_dish": milk_dish.id,
        }


@pytest.fixture
def domain_client(
    catalog_settings: Settings,
    catalog_session_factory: sessionmaker[Session],
) -> Iterator[TestClient]:
    _seed_domain(catalog_session_factory)
    app = create_app(catalog_settings, session_factory=catalog_session_factory)
    with TestClient(app) as client:
        yield client


def _get(client: TestClient, url: str, **params: object) -> object:
    return client.get(url, headers={"Host": LOCAL_HOST}, params=params)


def test_allergens_and_ingredients(domain_client: TestClient) -> None:
    allergens = _get(domain_client, "/api/allergens")
    assert allergens.status_code == 200
    payload = allergens.json()
    assert len(payload) == 15
    assert payload[0] == {"code": "gluten", "name": "Gluten"}
    assert payload[-1]["code"] == "unknown"

    ingredients = _get(domain_client, "/api/ingredients")
    assert ingredients.status_code == 200
    assert ingredients.json()["total"] == 5

    search = _get(domain_client, "/api/ingredients", q="ARR")
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["slug"] == "rice"

    by_group = _get(domain_client, "/api/ingredients", group="protein")
    assert by_group.json()["total"] == 1

    dairy = _get(domain_client, "/api/ingredients", group="dairy")
    assert dairy.json()["total"] == 1


def test_dishes_listing_filters_and_detail(domain_client: TestClient) -> None:
    all_dishes = _get(domain_client, "/api/dishes")
    assert all_dishes.status_code == 200
    assert all_dishes.json()["total"] == 3

    search = _get(domain_client, "/api/dishes", q="pollo")
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["slug"] == "chicken-rice"

    dinners = _get(domain_client, "/api/dishes", meal_type="dinner")
    assert dinners.json()["total"] == 3

    salads = _get(domain_client, "/api/dishes", tag="salad")
    assert salads.json()["total"] == 1

    light = _get(domain_client, "/api/dishes", light=True)
    assert light.json()["total"] == 1

    dish = all_dishes.json()["items"][0]
    detail = _get(domain_client, f"/api/dishes/{dish['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["ingredients"]) == 4
    assert detail.json()["allergens"] == []

    missing = _get(domain_client, "/api/dishes/99999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_profile_get_and_update(domain_client: TestClient) -> None:
    profile = _get(domain_client, "/api/profile")
    assert profile.status_code == 200
    assert profile.json()["people"] == 2
    assert profile.json()["days"] == 7
    assert profile.json()["allergen_codes"] == []

    updated = domain_client.put(
        "/api/profile",
        headers={"Host": LOCAL_HOST},
        json={"people": 3, "days": 5, "budget_cents": 5000, "allergen_codes": ["gluten"]},
    )
    assert updated.status_code == 200
    assert updated.json()["allergen_codes"] == ["gluten"]

    invalid_allergen = domain_client.put(
        "/api/profile",
        headers={"Host": LOCAL_HOST},
        json={"people": 3, "days": 5, "budget_cents": 5000, "allergen_codes": ["quimico"]},
    )
    assert invalid_allergen.status_code == 422
    assert invalid_allergen.json()["error"]["code"] == "VALIDATION_ERROR"

    invalid_people = domain_client.put(
        "/api/profile",
        headers={"Host": LOCAL_HOST},
        json={"people": 11, "days": 5, "budget_cents": 5000, "allergen_codes": []},
    )
    assert invalid_people.status_code == 422

    preserved = domain_client.put(
        "/api/profile",
        headers={"Host": LOCAL_HOST},
        json={"people": 4, "days": 6, "budget_cents": 6000},
    )
    assert preserved.status_code == 200
    assert preserved.json()["allergen_codes"] == ["gluten"]


def test_exclusions_crud_and_eligibility(domain_client: TestClient) -> None:
    ids = _seed_domain_ids(domain_client)
    dish_id = ids["chicken_rice"]

    created = domain_client.post(
        "/api/exclusions",
        headers={"Host": LOCAL_HOST},
        json={"dish_id": dish_id},
    )
    assert created.status_code == 201
    assertion = created.json()
    assert assertion["kind"] == "dish"
    assert assertion["label"] == "Pollo con arroz"

    duplicate = domain_client.post(
        "/api/exclusions",
        headers={"Host": LOCAL_HOST},
        json={"dish_id": dish_id},
    )
    assert duplicate.status_code == 422
    assert duplicate.json()["error"]["code"] == "INVALID_EXCLUSION"

    eligible = _get(domain_client, "/api/dishes", only_eligible="true")
    assert eligible.json()["total"] == 2

    listed = _get(domain_client, "/api/exclusions")
    assert len(listed.json()) == 1

    deleted = domain_client.delete(
        f"/api/exclusions/{assertion['id']}", headers={"Host": LOCAL_HOST}
    )
    assert deleted.status_code == 204
    assert _get(domain_client, "/api/exclusions").json() == []

    invalid_tag = domain_client.post(
        "/api/exclusions",
        headers={"Host": LOCAL_HOST},
        json={"tag": "inexistente"},
    )
    assert invalid_tag.status_code == 422

    invalid_dish = domain_client.post(
        "/api/exclusions",
        headers={"Host": LOCAL_HOST},
        json={"dish_id": 99999},
    )
    assert invalid_dish.status_code == 422


def _seed_domain_ids(client: TestClient) -> dict[str, int]:
    dishes = _get(client, "/api/dishes").json()["items"]
    by_slug = {dish["slug"]: dish["id"] for dish in dishes}
    ingredients = _get(client, "/api/ingredients").json()["items"]
    by_ingredient = {ingredient["slug"]: ingredient["id"] for ingredient in ingredients}
    return {
        "chicken_rice": by_slug["chicken-rice"],
        "rice_salad": by_slug["rice-salad"],
        "milk_dish": by_slug["milk-dessert"],
        "onion": by_ingredient["onion"],
        "milk": by_ingredient["milk"],
    }


def test_allergen_profile_filters_milk_dish(domain_client: TestClient) -> None:
    ids = _seed_domain_ids(domain_client)

    update = domain_client.put(
        "/api/profile",
        headers={"Host": LOCAL_HOST},
        json={"people": 2, "days": 7, "budget_cents": 7000, "allergen_codes": ["milk"]},
    )
    assert update.status_code == 200

    eligible = _get(domain_client, "/api/dishes", only_eligible="true")
    slugs = {item["slug"] for item in eligible.json()["items"]}
    assert "milk-dessert" not in slugs
    # La leche del postre está declarada: el producto no es elegible.
    milk_detail = _get(domain_client, f"/api/dishes/{ids['milk_dish']}")
    assert milk_detail.json()["eligible"] is False
    assert "ingredient_allergen" in milk_detail.json()["exclusion_reasons"]


def test_pantry_get_and_replace(domain_client: TestClient) -> None:
    ids = _seed_domain_ids(domain_client)

    updated = domain_client.put(
        "/api/pantry",
        headers={"Host": LOCAL_HOST},
        json={"items": [{"ingredient_id": ids["onion"], "quantity_milli": 500_000}]},
    )
    assert updated.status_code == 200
    assert updated.json()[0]["quantity_milli"] == 500_000
    assert updated.json()[0]["ingredient"]["base_unit"] == "g"

    fetched = _get(domain_client, "/api/pantry")
    assert fetched.status_code == 200
    assert len(fetched.json()) == 1

    invalid = domain_client.put(
        "/api/pantry",
        headers={"Host": LOCAL_HOST},
        json={"items": [{"ingredient_id": 99999, "quantity_milli": 1000}]},
    )
    assert invalid.status_code == 422

    duplicate = domain_client.put(
        "/api/pantry",
        headers={"Host": LOCAL_HOST},
        json={
            "items": [
                {"ingredient_id": ids["onion"], "quantity_milli": 1000},
                {"ingredient_id": ids["onion"], "quantity_milli": 2000},
            ]
        },
    )
    assert duplicate.status_code == 422


def test_ingredient_and_tag_exclusions_filter_catalog(domain_client: TestClient) -> None:
    ids = _seed_domain_ids(domain_client)

    ingredient_exclusion = domain_client.post(
        "/api/exclusions",
        headers={"Host": LOCAL_HOST},
        json={"ingredient_id": ids["onion"]},
    )
    assert ingredient_exclusion.status_code == 201
    tag_exclusion = domain_client.post(
        "/api/exclusions",
        headers={"Host": LOCAL_HOST},
        json={"tag": "salad"},
    )
    assert tag_exclusion.status_code == 201

    eligible = _get(domain_client, "/api/dishes", only_eligible="true")
    slugs = {item["slug"] for item in eligible.json()["items"]}
    assert "chicken-rice" not in slugs
    assert "rice-salad" not in slugs
    assert "milk-dessert" not in slugs
