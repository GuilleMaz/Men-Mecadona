# Backend de Cesta

API local en FastAPI + SQLite. Se ejecuta solo en `127.0.0.1`.

```powershell
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Salud: `GET http://127.0.0.1:8000/api/health` → `{"status":"ok"}`.
- Catálogo: `GET /api/catalog/status`, `POST /api/catalog/sync`,
  `GET /api/catalog/categories`, `GET /api/catalog/products?q=&category_id=&limit=&offset=`.
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

Inicialización explícita de la base y migraciones:

```powershell
uv run python ..\scripts\init_db.py
uv run alembic upgrade head
```

Alembic usa `render_as_batch=True` para SQLite y toma la URL de `Settings`
(`CESTA_DATA_DIR`); no hay rutas hardcodeadas en `alembic.ini`.

## Catálogo (F1)

- Tablas: `categories`, `products`, `sync_runs`, `sync_category_runs` y
  `product_allergens`. No se guarda `raw_json` ni histórico de precios.
- La sync descarga 26 secciones y 152 subcategorías con concurrencia máxima 4,
  reintentos con backoff y upsert idempotente por `external_id`.
- Una subcategoría fallida no marca sus productos como no disponibles; la sync
  queda en `partial` y conserva la disponibilidad anterior.
- Los precios se guardan en céntimos enteros y las cantidades en milésimas de
  g/ml/unidad. `unit_price` es el precio del paquete.
- Los productos de mostrador o peso variable (`approx_size` o
  `selling_method != 0`) quedan fuera del futuro mapeo de ingredientes.
- El arranque refresca el catálogo en segundo plano si está vacío o tiene más de
  24 h; no bloquea la UI.

Sync manual y comprobación real:

```powershell
uv run alembic upgrade head
uv run python ..\scripts\sync_catalog.py
```

Los tests no llaman a Mercadona: usan fixtures sintéticas y `respx`.

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
