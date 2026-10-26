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
- Dominio: `GET /api/allergens`, `GET /api/ingredients`, `GET /api/dishes`,
  `GET /api/dishes/{id}`, `GET/PUT /api/profile`, `GET/POST/DELETE /api/exclusions`,
  `GET/PUT /api/pantry`, `POST /api/pricing/preview`.
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
ingredientes y platos viven en `app/data/`.

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

## Ingredientes, platos y preferencias (F2)

- `app/data/ingredients.yaml`: 110 ingredientes con unidad base, grupo, ración,
  alérgenos y 1-3 productos por `external_id`. Un producto pertenece a un solo
  ingrediente.
- `app/data/dishes.yaml`: 60 platos sin pasos; los flags `has_vegetables`,
  `light`, `carbs` y `protein_sources` se derivan de la composición.
- Cargador idempotente, `seed_version` por hash, soft delete y `--dry-run`.
- Alérgenos: `GET /api/allergens`, parser de detalle con `x99` y política
  fail-closed. Solo se descarga el detalle de los productos mapeados.
- Perfil único, exclusiones por ingrediente/plato/etiqueta y despensa en
  milésimas de la unidad base.

```powershell
uv run python ..\scripts\load_seed.py --dry-run
uv run python ..\scripts\load_seed.py
uv run python ..\scripts\sync_allergens.py
uv run python ..\scripts\validate_seed.py
```

`sync_catalog.py` también recarga el seed y sincroniza alérgenos tras una sync
correcta.

## Coste y preview (F3)

- `app/services/pricing.py` concentra el motor puro: escalado por personas y
  raciones, formatos comprables, necesidad neta con despensa, `plan_purchase`,
  consumo, ticket y sobras.
- Cantidades en milésimas y céntimos enteros; `Decimal` solo para costes
  unitarios intermedios y redondeo half-up al final.
- `plan_purchase` minimiza el ticket y permite mezclar formatos; desempata por
  menos paquetes y `product_id`. F4 reutiliza la misma función para la lista.
- La identidad `ticket + pantry_consumption = consumption + leftover` se cumple
  por ingrediente y por cesta.
- `POST /api/pricing/preview` no persiste menús ni aplica filtros de alérgenos.
  Recibe `people`, `dishes` y `pantry` opcional (si falta, usa la del perfil).
  Devuelve coste por plato y ración, ingredientes, paquetes y totales. Un
  ingrediente sin producto comprable devuelve `409 PRODUCT_UNAVAILABLE`.
- `grams_per_unit` es obligatorio en ingredientes con `base_unit=unit`.

```powershell
uv run pytest tests/test_pricing.py tests/test_pricing_api.py
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
