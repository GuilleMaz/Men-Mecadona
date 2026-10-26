"""Configuración: valores por defecto, directorio de datos y validaciones."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import EXPECTED_WAREHOUSE, POSTAL_CODE, Settings


def test_defaults_are_safe_for_local_use() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "local"
    assert settings.sync_on_startup is True
    assert settings.optimizer_time_limit_seconds == 8
    assert settings.is_development is True


def test_data_dir_defaults_to_local_app_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    settings = Settings(_env_file=None)

    assert settings.data_dir == tmp_path / "Cesta"
    assert settings.database_path == tmp_path / "Cesta" / "cesta.db"
    assert settings.database_url.endswith("/Cesta/cesta.db")
    assert settings.database_url.startswith("sqlite:///")


def test_explicit_data_dir_must_be_absolute(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, cesta_data_dir=tmp_path / "datos")

    assert settings.data_dir == tmp_path / "datos"


def test_relative_data_dir_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ruta absoluta"):
        Settings(_env_file=None, cesta_data_dir=Path("datos"))


def test_data_dir_inside_onedrive_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="OneDrive"):
        Settings(_env_file=None, cesta_data_dir=tmp_path / "OneDrive" / "Cesta")


def test_allowed_hosts_are_local_only() -> None:
    settings = Settings(_env_file=None)

    assert settings.allowed_hosts == frozenset({"127.0.0.1", "localhost", "::1"})


def test_cors_only_in_development() -> None:
    development = Settings(_env_file=None, app_env="development")
    production = Settings(_env_file=None, app_env="production")

    assert development.cors_origins == ["http://localhost:5173"]
    assert production.cors_origins == []


def test_mvp_location_constants() -> None:
    assert POSTAL_CODE == "22002"
    assert EXPECTED_WAREHOUSE == "4389"
