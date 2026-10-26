# Backend de Cesta

API local en FastAPI + SQLite. Se ejecuta solo en `127.0.0.1`.

```powershell
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Salud: `GET http://127.0.0.1:8000/api/health` → `{"status":"ok"}`.
- Documentación interactiva: `http://127.0.0.1:8000/docs`.

Para arrancar backend y frontend juntos, usa `.\run.ps1` desde la raíz. Para
ejecutar toda la calidad del repositorio, usa `.\check.ps1`.

Calidad:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```

La base de datos vive en `%LOCALAPPDATA%\Cesta\cesta.db` (o en `CESTA_DATA_DIR`),
fuera de OneDrive. Se rechaza una ruta de datos dentro de OneDrive. Los YAML de
ingredientes y platos irán en `app/data/`.

Inicialización explícita de la base:

```powershell
uv run python ..\scripts\init_db.py
```

Seguridad local: el middleware de `Host` solo acepta `127.0.0.1`, `localhost` y
`::1`; el resto devuelve `400 INVALID_HOST`. Los tests de API envían un `Host`
local explícito porque el `testserver` por defecto de TestClient se rechaza.
Ver `SECURITY.md` en la raíz.

## Spike de OR-Tools (F0.6)

```powershell
uv run python ..\scripts\spike_ortools.py
```

Resuelve un modelo toy con 28 huecos, 60 platos, 120 ingredientes, paquetes,
presupuesto y variedad con `num_search_workers=1`. Mide el tiempo y valida la
solución; no es el optimizador definitivo de F4.

## Cliente Mercadona (F0.4)

```powershell
uv run python ..\scripts\check_mercadona.py
```

Fija el CP 22002, exige que la API confirme el almacén 4389 y muestra el número de
secciones y subcategorías, además de un producto parseado de una subcategoría. No
descarga el catálogo completo ni guarda respuestas.

Los tests usan fixtures sintéticas y `respx`: **nunca** llaman a Mercadona.
