"""Motor SQLite: PRAGMA obligatorios y ubicación fuera del repositorio."""

from pathlib import Path

from app.config import Settings
from app.db import create_db_engine


def _settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, cesta_data_dir=tmp_path / "datos")


def test_sqlite_pragmas_are_applied(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = create_db_engine(settings)

    try:
        with engine.connect() as connection:
            foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
            busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()
            journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
    finally:
        engine.dispose()

    assert foreign_keys == 1
    assert busy_timeout == 5000
    assert str(journal_mode).lower() == "wal"


def test_engine_creates_data_dir_and_database_file(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = create_db_engine(settings)

    try:
        with engine.connect():
            pass
    finally:
        engine.dispose()

    assert settings.database_path.is_file()
    assert settings.database_path.parent == tmp_path / "datos"
