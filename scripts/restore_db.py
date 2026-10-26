"""Restaura una copia verificada de SQLite sobre la base de Cesta (F5.3).

Pasos seguros:

1. Cierra la app (`Ctrl+C` en `run.ps1`).
2. Ejecuta este script con la copia elegida y `--force` si ya existe una base.
3. Arranca de nuevo; `run.ps1` aplica las migraciones pendientes.

La copia se valida con `PRAGMA integrity_check` y se comprueba que tiene el
esquema de Cesta. La escritura es atómica: primero se copia a un temporal y
después se reemplaza la base. Se eliminan `-wal` y `-shm` antiguos.

Uso desde la raíz:

    cd backend
    uv run python ..\\scripts\\restore_db.py --backup D:\\copias\\cesta.db --force
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from backup_db import inspect_database  # noqa: E402

from app.config import get_settings  # noqa: E402


def restore_database(backup: Path, destination: Path, *, force: bool = False) -> Path:
    """Restaura `backup` en `destination` de forma atómica y verificada."""
    inspect_database(backup)
    if destination.exists() and not force:
        raise FileExistsError(
            f"Ya existe la base de datos {destination}. Usa --force para reemplazarla."
        )

    wal = destination.with_name(f"{destination.name}-wal")
    shm = destination.with_name(f"{destination.name}-shm")
    if not force and (wal.exists() or shm.exists()):
        raise RuntimeError("Hay archivos WAL/SHM de una base en uso. Detén la app o usa --force.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.restore.tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        shutil.copy2(backup, temporary)
        inspect_database(temporary)
        for stale in (wal, shm):
            if stale.exists():
                stale.unlink()
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Restaura una copia de Cesta.")
    parser.add_argument("--backup", type=Path, required=True, help="Copia a restaurar.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reemplaza la base existente y descarta WAL/SHM antiguos.",
    )
    args = parser.parse_args(argv)

    try:
        result = restore_database(args.backup, settings.database_path, force=args.force)
    except (FileNotFoundError, FileExistsError, RuntimeError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Base restaurada y verificada: {result}")
    print("Arranca la app con .\\run.ps1 para aplicar migraciones pendientes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
