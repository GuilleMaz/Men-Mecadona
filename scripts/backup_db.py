"""Copia de seguridad consistente de la base SQLite de Cesta (F5.3).

Usa la API de backup de SQLite, que copia una instantánea coherente incluso con
WAL. Aun así, para una copia manual se recomienda cerrar la app antes de
ejecutarlo. El archivo resultante se verifica con `PRAGMA integrity_check` y se
comprueba que contiene el esquema de Cesta.

Uso desde la raíz:

    cd backend
    uv run python ..\\scripts\\backup_db.py
    uv run python ..\\scripts\\backup_db.py --output D:\\copias\\cesta.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402

REQUIRED_TABLES = frozenset({"alembic_version", "products", "menus"})


def inspect_database(path: Path) -> None:
    """Valida integridad y esquema de una copia o base SQLite."""
    if not path.is_file():
        raise FileNotFoundError(f"No existe la base de datos: {path}")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise RuntimeError(f"SQLite no pasó integrity_check: {integrity!r}")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = REQUIRED_TABLES - tables
        if missing:
            raise RuntimeError(
                "La copia no parece una base de Cesta; faltan tablas: " + ", ".join(sorted(missing))
            )
    finally:
        connection.close()


def backup_database(source: Path, destination: Path) -> Path:
    """Copia `source` en `destination` y valida el resultado."""
    if not source.is_file():
        raise FileNotFoundError(f"No existe la base de datos de origen: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(
            f"El destino ya existe: {destination}. Elige otro nombre o bórralo antes."
        )

    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()

    inspect_database(destination)
    return destination


def default_backup_path(data_dir: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%SZ")
    return data_dir / "backups" / f"cesta-{stamp}.db"


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Copia de seguridad de Cesta.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ruta del archivo de copia. Por defecto, data_dir/backups/cesta-<fecha>.db",
    )
    args = parser.parse_args(argv)
    destination = args.output or default_backup_path(settings.data_dir)

    try:
        result = backup_database(settings.database_path, destination)
    except (FileNotFoundError, FileExistsError, RuntimeError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}")
        return 1

    size_kb = result.stat().st_size / 1024
    print(f"Copia verificada: {result} ({size_kb:.1f} KiB)")
    print("La app debe estar parada si vas a restaurar esta copia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
