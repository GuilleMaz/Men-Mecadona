"""Inicializa el directorio de datos y el archivo SQLite de Cesta (F0.7).

La base vive fuera de OneDrive, por defecto en `%LOCALAPPDATA%\\Cesta`. El script
crea el directorio y el archivo, aplica los PRAGMA y comprueba la ubicación.

Uso desde la raíz del repositorio:

    backend\\.venv\\Scripts\\python.exe scripts\\init_db.py

o:

    cd backend
    uv run python ..\\scripts\\init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import PROJECT_ROOT, get_settings  # noqa: E402
from app.db import create_db_engine  # noqa: E402


def main() -> int:
    settings = get_settings()
    data_dir = settings.data_dir.resolve()

    if data_dir.is_relative_to(PROJECT_ROOT.resolve()):
        print("ERROR: CESTA_DATA_DIR no puede estar dentro del repositorio.")
        return 1
    if any(part.casefold() == "onedrive" for part in data_dir.parts):
        print("ERROR: CESTA_DATA_DIR no puede estar dentro de OneDrive.")
        return 1

    engine = create_db_engine(settings)
    try:
        with engine.connect() as connection:
            journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
            foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
            busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()
    finally:
        engine.dispose()

    if not settings.database_path.is_file():
        print("ERROR: no se ha creado el archivo de la base de datos.")
        return 1

    print(f"Directorio de datos: {data_dir}")
    print(f"Base de datos: {settings.database_path}")
    print(
        f"PRAGMA: journal_mode={journal_mode}, "
        f"foreign_keys={foreign_keys}, busy_timeout={busy_timeout}"
    )
    print("Base de datos inicializada fuera de OneDrive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
