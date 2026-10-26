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
- Menús: `POST /api/menus/generate`, `GET /api/menus`, `GET /api/menus/{id}`,
  `PATCH /api/menus/{id}/entries/{entry_id}`,
  `POST /api/menus/{id}/entries/{entry_id}/swap|exclude`,
  `POST /api/menus/{id}/regenerate|revalidate`,
  `GET /api/menus/{id}/shopping-list`,
  `PATCH /api/menus/{id}/shopping-list/items/{item_id}` y
  `GET /api/menus/{id}/export?format=markdown|csv`.
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

## Menús y optimizador (F4.1-F4.9)

- `app/models/menu.py`: `menus`, `menu_entries`, `menu_entry_ingredients` y
  `shopping_items`, con snapshot de nombre, coste, proteína y precios de compra.
  Migraciones `20261026_0003`, `20261026_0004` (relajaciones) y `20261026_0005`
  (ticket anterior, fecha de revalidación e índices de entrega).
- `app/schemas/menu.py`: `MenuSettings` versionado con alérgenos, exclusiones,
  despensa, `max_repeats` y versión del optimizador.
  `app/schemas/menu_api.py`: contrato de entrada/salida de la API.
- `app/services/optimizer.py`: CP-SAT en dos etapas (variedad y ticket), con
  presupuesto duro, demanda por paquetes elegibles `P_i`, mínimos diarios,
  pista greedy, fallback sin presupuesto y diagnóstico de `budget`, `repeats`,
  `minimums`, `locks` y `no_assignment`.
- `app/services/menu_service.py`: persistencia y recálculo transaccional, lista
  materializada con `plan_purchase`, reparto exacto de céntimos por entrada,
  conservación de `checked`, snapshot de composición por entrada, validación de
  sync 22002/4389 y mutaciones `swap`/`exclude`/`regenerate`/`revalidate`/«ya lo
  tengo». La revalidación no persiste un ticket por encima del presupuesto.
- `app/api/menus.py`: API fina sobre el servicio. `generate` hereda del perfil
  los campos omitidos, devuelve el preview `infeasible`/`timeout` sin persistir y
  mapea `MenuServiceError`/`OptimizerError` al sobre homogéneo. La lista agrupa
  por sección, incluye el snapshot de despensa y calcula coste por comida, día y
  persona. `PATCH .../shopping-list/items/{id}` acepta `checked` o
  `already_have`; el export CSV neutraliza fórmulas (`=`, `+`, `-`, `@`).
- Tests: horizontes y personas, presupuesto exacto/imposible, pescado, alérgeno
  `unknown`, producto compartido, `base_servings`, bloqueos/regeneración,
  preview contra lista y `num_search_workers=1` con semilla fija.

```powershell
uv run pytest tests/test_menus_api.py tests/test_optimizer.py tests/test_menu_horizons.py tests/test_menu_service.py tests/test_menu_integration.py
```

Dry-run y benchmark manuales, sin persistir menús:

```powershell
uv run python ..\scripts\dry_run_menu.py --days 1,2,7,14 --people 1,2,4,10
uv run python ..\scripts\benchmark_menu.py --runs 20 --days 14 --people 4
```

Estado actual: 354 tests backend en verde; benchmark 14d/4p con p95 3,73 s.

## Calidad, resiliencia y entrega (F5)

- `app/services/price_source.py`: resuelve si la copia local sirve para precios
  actuales. Solo es válida si la última sync completa es de CP 22002 / almacén
  4389. Una sync fallida posterior permite consultar y revalidar menús, pero
  bloquea la generación de menús nuevos. Una copia de otro almacén no se mezcla.
- `MenuService` guarda `previous_ticket_cents`, `revalidated_ticket_cents`,
  `price_delta_cents` y `revalidated_at` para que la UI muestre el delta sin
  romper el snapshot válido. `GET/POST` de menús y la lista exponen esos campos.
- `app/static.py`: en `APP_ENV=production`, FastAPI sirve `frontend/dist` en el
  mismo puerto con fallback a `index.html` para las rutas del cliente. `/docs`,
  `/redoc` y `/api/*` inexistentes no devuelven la SPA.
- `run.ps1 -Prod` compila el frontend, arranca un único proceso Uvicorn sin
  recarga y desactiva CORS.
- `scripts/backup_db.py` y `scripts/restore_db.py`: copia consistente con la API
  de SQLite, `integrity_check`, validación de esquema y restauración atómica.
- `scripts/benchmark_endpoints.py`: p50/p95 de `/api/health`, `/api/dishes`,
  `/api/catalog/status` y `/api/menus` contra la copia local.
- `audit.ps1`: `pip-audit` + `npm audit --audit-level=high`; última ejecución sin
  hallazgos.
- `tests/test_delivery.py`: flujo completo generar → detalle → lista, historial
  inmutable, contrato sin pasos y privacidad (sin telemetría ni hosts no
  declarados). `tests/test_production_build.py` cubre el build servido y
  `tests/test_backup_restore.py` la copia/restauración.

```powershell
uv run pytest tests/test_delivery.py tests/test_backup_restore.py tests/test_production_build.py
uv run python ..\scripts\benchmark_endpoints.py --runs 20
uv run python ..\scripts\backup_db.py
```

Benchmark de endpoints en el equipo de desarrollo: `/api/dishes` p95 32,00 ms
(límite 200 ms), `/api/catalog/status` p95 9,91 ms y `/api/menus` p95 5,58 ms.
Sync real: 152/152 subcategorías, 4.542 productos vistos, 4.292 únicos, 7,72 s.

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
