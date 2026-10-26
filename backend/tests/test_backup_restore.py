"""Backup y restore de SQLite (F5.3)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import backup_db  # noqa: E402
import restore_db  # noqa: E402


def _create_cesta_db(path: Path, marker: str = "original") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY);
            CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE menus (id INTEGER PRIMARY KEY, status TEXT);
            """
        )
        connection.execute("INSERT INTO alembic_version VALUES ('20261026_0005')")
        connection.execute("INSERT INTO products VALUES (1, ?)", (marker,))
        connection.execute("INSERT INTO menus VALUES (1, 'optimal')")
        connection.commit()
    finally:
        connection.close()


def _read_product(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute("SELECT name FROM products WHERE id = 1").fetchone()
        assert row is not None
        return str(row[0])
    finally:
        connection.close()


def test_backup_copies_and_validates_database(tmp_path: Path) -> None:
    source = tmp_path / "cesta.db"
    _create_cesta_db(source)

    destination = backup_db.backup_database(source, tmp_path / "backups" / "cesta.db")

    assert destination.is_file()
    assert _read_product(destination) == "original"
    backup_db.inspect_database(destination)


def test_backup_refuses_to_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "cesta.db"
    _create_cesta_db(source)
    destination = tmp_path / "backup.db"
    destination.write_bytes(b"no soy una base")

    with pytest.raises(FileExistsError):
        backup_db.backup_database(source, destination)


def test_inspect_rejects_a_non_cesta_database(tmp_path: Path) -> None:
    path = tmp_path / "otra.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE foo (id INTEGER)")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="faltan tablas"):
        backup_db.inspect_database(path)


def test_restore_replaces_database_only_with_force(tmp_path: Path) -> None:
    backup = tmp_path / "backup.db"
    _create_cesta_db(backup, marker="restaurada")
    destination = tmp_path / "cesta.db"
    _create_cesta_db(destination, marker="actual")

    with pytest.raises(FileExistsError):
        restore_db.restore_database(backup, destination)

    restored = restore_db.restore_database(backup, destination, force=True)
    assert restored == destination
    assert _read_product(destination) == "restaurada"
    assert not destination.with_name("cesta.db.restore.tmp").exists()


def test_restore_rejects_invalid_backup(tmp_path: Path) -> None:
    invalid = tmp_path / "invalida.db"
    invalid.write_bytes(b"basura")
    destination = tmp_path / "cesta.db"

    with pytest.raises(sqlite3.DatabaseError):
        restore_db.restore_database(invalid, destination, force=True)
    assert not destination.exists()
