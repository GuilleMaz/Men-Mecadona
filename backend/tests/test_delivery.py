"""Flujo de entrega, contrato sin pasos y privacidad (F5.2/F5.7)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api import menus as menus_module
from app.config import Settings
from app.main import create_app
from app.models.dishes import Dish
from tests.domain_fixtures import make_profile, make_sync_run
from tests.optimizer_fixtures import build_balanced_catalog

LOCAL_HOST = "127.0.0.1:8000"
HEADERS = {"Host": LOCAL_HOST}
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_TRACKERS = (
    "google-analytics",
    "googletagmanager",
    "sentry.io",
    "posthog",
    "mixpanel",
    "segment.io",
    "datadog",
    "newrelic",
    "hotjar",
    "clarity.ms",
)


@pytest.fixture
def delivery_client(
    catalog_settings: Settings,
    catalog_session_factory: sessionmaker[Session],
) -> TestClient:
    with catalog_session_factory() as session:
        make_profile(session, people=2, days=1, budget_cents=1_000_000)
        make_sync_run(session)
        build_balanced_catalog(session, days=1)
        session.commit()
    return TestClient(create_app(catalog_settings, session_factory=catalog_session_factory))


def test_full_flow_generate_view_and_shopping_list(
    delivery_client: TestClient,
    catalog_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    catalog_session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(
        menus_module,
        "get_settings",
        lambda: catalog_settings.model_copy(update={"optimizer_time_limit_seconds": 2}),
    )

    generated = delivery_client.post(
        "/api/menus/generate",
        headers=HEADERS,
        json={"people": 2, "days": 1, "budget_cents": 1_000_000},
    )
    assert generated.status_code == 200, generated.text
    payload = generated.json()
    assert payload["menu_id"] is not None
    assert len(payload["entries"]) == 2
    menu_id = payload["menu_id"]

    detail = delivery_client.get(f"/api/menus/{menu_id}", headers=HEADERS)
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["entries"]) == 2
    assert {entry["slot"] for entry in body["entries"]} == {"lunch", "dinner"}
    for entry in body["entries"]:
        assert "steps" not in entry
        assert "instructions" not in entry
        assert "recipe" not in entry

    shopping = delivery_client.get(f"/api/menus/{menu_id}/shopping-list", headers=HEADERS)
    assert shopping.status_code == 200
    cart = shopping.json()
    assert cart["ticket_cents"] == body["ticket_cents"]
    assert cart["ticket_cents"] == sum(section["subtotal_cents"] for section in cart["sections"])
    assert (
        cart["ticket_cents"] + cart["pantry_consumption_cents"]
        == cart["consumption_cents"] + cart["leftover_value_cents"]
    )

    history = delivery_client.get("/api/menus", headers=HEADERS)
    assert history.status_code == 200
    assert history.json()["items"][0]["id"] == menu_id
    assert history.json()["items"][0]["ticket_cents"] == body["ticket_cents"]

    # El snapshot del historial no cambia aunque el plato se renombre después.
    frozen_name = body["entries"][0]["dish_name"]
    frozen_dish_id = body["entries"][0]["dish_id"]
    with catalog_session_factory() as session:
        dish = session.scalar(select(Dish).where(Dish.id == frozen_dish_id))
        assert dish is not None
        dish.name = "Nombre cambiado después"
        session.commit()

    reopened = delivery_client.get(f"/api/menus/{menu_id}", headers=HEADERS).json()
    assert (
        next(entry for entry in reopened["entries"] if entry["dish_id"] == frozen_dish_id)[
            "dish_name"
        ]
        == frozen_name
    )


def test_dish_catalog_has_no_cooking_steps_or_recipe_keys() -> None:
    raw = yaml.safe_load(
        (PROJECT_ROOT / "backend" / "app" / "data" / "dishes.yaml").read_text(encoding="utf-8")
    )
    dishes = raw["dishes"] if isinstance(raw, dict) else raw
    assert isinstance(dishes, list) and dishes

    forbidden = {"steps", "instructions", "recipe", "recipes", "elaboration", "preparation"}
    for dish in dishes:
        assert isinstance(dish, dict)
        assert forbidden.isdisjoint(dish), dish.get("slug")


def test_no_telemetry_or_undeclared_external_hosts() -> None:
    frontend_sources = list((PROJECT_ROOT / "frontend" / "src").rglob("*.ts")) + list(
        (PROJECT_ROOT / "frontend" / "src").rglob("*.tsx")
    )
    frontend_text = "\n".join(path.read_text(encoding="utf-8") for path in frontend_sources)
    lowered = frontend_text.casefold()
    for tracker in FORBIDDEN_TRACKERS:
        assert tracker not in lowered
    assert "navigator.sendbeacon" not in lowered
    assert "new websocket(" not in lowered
    assert "new eventsource(" not in lowered

    backend_sources = list((PROJECT_ROOT / "backend" / "app").rglob("*.py"))
    backend_text = "\n".join(path.read_text(encoding="utf-8") for path in backend_sources)
    urls = set(re.findall(r"https?://[^\s\"')]+", backend_text))
    allowed = {
        "http://localhost:5173",
        "https://tienda.mercadona.es",
        "http://127.0.0.1:8000",
    }
    assert urls <= allowed, urls - allowed
