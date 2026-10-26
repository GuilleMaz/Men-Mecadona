"""Snapshot validado de preferencias de menú (F4.1)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas.menu import MenuSettings, PantrySnapshot


def test_menu_settings_defaults() -> None:
    settings = MenuSettings()

    assert settings.version == 1
    assert settings.allergen_codes == []
    assert settings.excluded_ingredient_ids == []
    assert settings.excluded_dish_ids == []
    assert settings.excluded_tags == []
    assert settings.pantry == []
    assert settings.max_repeats == 1
    assert settings.optimizer_version == "1"


def test_menu_settings_rejects_unknown_allergen() -> None:
    with pytest.raises(ValidationError, match="Alérgeno desconocido"):
        MenuSettings(allergen_codes=["shellfish"])


def test_menu_settings_deduplicates_allergens() -> None:
    settings = MenuSettings(allergen_codes=["gluten", "milk", "gluten", "milk"])

    assert settings.allergen_codes == ["gluten", "milk"]


def test_menu_settings_deduplicates_ids() -> None:
    settings = MenuSettings(
        excluded_ingredient_ids=[3, 1, 3],
        excluded_dish_ids=[2, 2, 5],
    )

    assert settings.excluded_ingredient_ids == [3, 1]
    assert settings.excluded_dish_ids == [2, 5]


def test_menu_settings_normalizes_and_deduplicates_tags() -> None:
    settings = MenuSettings(excluded_tags=[" cena ", "cena", "rápido", " rápido"])

    assert settings.excluded_tags == ["cena", "rápido"]


def test_menu_settings_rejects_duplicate_pantry_ingredient() -> None:
    with pytest.raises(ValidationError, match="repetidos en la despensa"):
        MenuSettings(
            pantry=[
                PantrySnapshot(ingredient_id=1, quantity_milli=0),
                PantrySnapshot(ingredient_id=1, quantity_milli=500_000),
            ]
        )


@pytest.mark.parametrize("max_repeats", [0, 15])
def test_menu_settings_rejects_max_repeats_out_of_range(max_repeats: int) -> None:
    with pytest.raises(ValidationError):
        MenuSettings(max_repeats=max_repeats)


@pytest.mark.parametrize("max_repeats", [1, 14])
def test_menu_settings_accepts_max_repeats_bounds(max_repeats: int) -> None:
    assert MenuSettings(max_repeats=max_repeats).max_repeats == max_repeats


def test_menu_settings_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MenuSettings(allergen_codes=[], unexpected=True)  # type: ignore[call-arg]


def test_pantry_snapshot_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PantrySnapshot(ingredient_id=1, quantity_milli=0, unit="g")  # type: ignore[call-arg]


def test_menu_settings_json_roundtrip() -> None:
    settings = MenuSettings(
        version=2,
        allergen_codes=["gluten", "milk"],
        excluded_ingredient_ids=[1, 2],
        excluded_dish_ids=[7],
        excluded_tags=["rápido"],
        pantry=[PantrySnapshot(ingredient_id=3, quantity_milli=500_000)],
        max_repeats=3,
        optimizer_version="2026.10",
    )

    restored = MenuSettings.model_validate(json.loads(settings.model_dump_json()))

    assert restored == settings
