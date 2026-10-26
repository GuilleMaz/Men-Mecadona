"""Fixtures compartidas de los tests de catálogo."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import Base, create_db_engine
from app.models import Category, Product, SyncRun  # noqa: F401 - registra las tablas


@pytest.fixture(autouse=True)
def isolated_local_app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Evita que los tests toquen la base real de `%LOCALAPPDATA%`."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))


@pytest.fixture
def catalog_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        sync_on_startup=False,
        cesta_data_dir=tmp_path / "datos",
    )


@pytest.fixture
def catalog_session_factory(
    catalog_settings: Settings,
) -> Iterator[sessionmaker[Session]]:
    engine = create_db_engine(catalog_settings)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()
