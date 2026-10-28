# Architecture

## Estructura

```text
MERCADONA/
├── PLAN.md
├── TASKS.md
├── AGENTS.md
├── README.md
├── SECURITY.md
├── .env.example
├── .gitignore
├── project-memory/
├── backend/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── .python-version
│   ├── README.md
│   ├── alembic.ini        # migraciones (URL desde Settings)
│   ├── alembic/           # env.py, script.py.mako, versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # create_app(), CORS, Host, lifespan y sync de arranque
│   │   ├── config.py        # Settings, ruta de datos, CP 22002 / almacén 4389
│   │   ├── db.py            # motor SQLite, PRAGMA, Base, sesiones
│   │   ├── security.py      # allowlist de Host local
│   │   ├── allergens.py     # lista canónica y etiquetas de alérgenos
│   │   ├── static.py        # servido del frontend compilado con fallback SPA
│   │   ├── api/             # health, catalog, domain, pricing, menus, presenters, errors
│   │   ├── schemas/         # health.py, mercadona.py, catalog.py, seed.py, domain.py, pricing.py, menu.py, menu_api.py
│   │   ├── models/          # catalog.py, ingredients.py, dishes.py, profile.py, menu.py, types.py
│   │   ├── services/        # mercadona_client.py, catalog_normalizer.py, catalog_sync.py,
│   │   │                    # seed.py, allergen_sync.py, eligibility.py, pricing.py,
│   │   │                    # optimizer.py, menu_service.py, price_source.py
│   │   └── data/            # ingredients.yaml, dishes.yaml
│   └── tests/               # API, config, db, seguridad, cliente, catálogo, dominio,
│                            # coste, optimizador, menús y fixtures
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── components.json      # shadcn/ui (style new-york, Tailwind 4)
│   ├── vite.config.ts       # alias @/*, Tailwind, proxy /api, Vitest
│   ├── eslint.config.js
│   ├── .prettierrc.json
│   └── src/
│       ├── main.tsx         # QueryClient + BrowserRouter
│       ├── App.tsx          # rutas
│       ├── index.css        # Tailwind 4 + tema shadcn/ui
│       ├── components/
│       │   ├── catalog/CatalogStatusCard.tsx
│       │   ├── dishes/DishCostCard.tsx
│       │   ├── layout/AppLayout.tsx
│       │   ├── layout/BackendStatus.tsx
│       │   ├── menu/        # BudgetBar, MenuEntryCard, MenuGrid, MenuHeader, diálogos
│       │   ├── preferences/AllergenPreferencesCard.tsx
│       │   ├── preferences/ExclusionsCard.tsx
│       │   ├── preferences/PantryCard.tsx
│       │   ├── shopping/    # ShoppingSection, ShoppingTotals, ShoppingPantry
│       │   └── ui/          # button, card, input, label, dialog
│       ├── pages/           # MenuPage, MenuDetailPage, ShoppingListPage, HistoryPage, DishesPage, SettingsPage, NotFoundPage
│       ├── lib/             # utils.ts, catalog.ts, domain.ts, menu.ts, labels.ts
│       └── test/            # setup, servidor MSW, render-app
├── scripts/                 # check_mercadona.py, spike_catalog.py, spike_ortools.py,
│                            # init_db.py, sync_catalog.py, load_seed.py,
│                            # validate_seed.py, sync_allergens.py, dry_run_menu.py,
│                            # benchmark_menu.py, benchmark_endpoints.py,
│                            # backup_db.py, restore_db.py
├── run.ps1                  # dev/Vite o -Prod (build + un solo proceso), SQLite fuera de OneDrive
├── check.ps1                # lint + tipos + tests + build
├── audit.ps1                # pip-audit + npm audit (high/critical)
└── finish-phase.ps1         # calidad + commit + push a GitHub
```

`backend/app` es un paquete plano (no se distribuye): `uv` usa `package = false` y
pytest resuelve `app` con `pythonpath = ["."]` desde `backend/`.

## Componentes

- **Frontend React:** layout en español con navegación Menú / Historial / Platos / Ajustes, formulario persistente de personas/días/presupuesto, generación con modal de menú inviable, rejilla días × comida/cena con principal y acompañamiento, barra de presupuesto, acciones de bloqueo/swap/exclusión/añadir-quitar acompañamiento/regeneración, revalidación al abrir con delta de precios, lista de la compra con secciones, checkboxes y «ya lo tengo», historial paginado, catálogo de platos con búsqueda, filtro por curso y filtros, detalle con ingredientes y «no me gusta», tarjeta de coste de consumo/ticket por plato y ración, tarjeta de estado del catálogo, origen de precios y tarjetas de alérgenos, exclusiones y despensa. Incluye enlace «Saltar al contenido», foco visible y hoja de impresión A4.
- **FastAPI:** API REST, validación Pydantic, orquestación de servicios, errores homogéneos (`{"error": {...}}`), `/api/health`, `/api/catalog/*`, `/api/*` de dominio y `/api/menus/*`. La sync de arranque y la carga del seed corren en segundo plano desde el lifespan. En `APP_ENV=production` sirve `frontend/dist` con fallback SPA y desactiva `/docs`/`/redoc`.
- **Configuración (`app/config.py`):** `Settings` con `APP_ENV`, `SYNC_ON_STARTUP`, `OPTIMIZER_TIME_LIMIT_SECONDS` y `CESTA_DATA_DIR` opcional absoluto. Rechaza rutas dentro de OneDrive. Constantes `POSTAL_CODE="22002"`, `EXPECTED_WAREHOUSE="4389"` y `LOCAL_HOSTS`.
- **Seguridad (`app/security.py`):** `HostValidationMiddleware` acepta solo `127.0.0.1`, `localhost` y `::1`; el resto devuelve `400 INVALID_HOST`.
- **Persistencia (`app/db.py`):** motor SQLite con `foreign_keys=ON`, WAL y `busy_timeout=5000`; `Base` declarativa y sesión por petición. `create_engine_for_url` permite que Alembic y los tests usen una URL concreta.
- **MercadonaClient:** cliente asíncrono implementado (F0.4); fija CP 22002, valida almacén 4389, descarga secciones, subcategorías y detalle de producto. Ver sección propia y el informe del spike en `decisions.md`.
- **CatalogSyncService:** sync idempotente implementada (F1.4): árbol de categorías, concurrencia 4, reintentos del cliente, progreso por subcategoría, fallo parcial, lock de proceso y recuperación de syncs interrumpidas. El arranque refresca en segundo plano si faltan productos o la última copia tiene más de 24 h. Al terminar, recarga el seed y enriquece alérgenos.
- **CatalogNormalizer:** funciones puras con `Decimal` (F1.3): importes a céntimos, `unit_size`/`size_format` a milésimas de g/ml/unidad, packs, mostrador y `is_food` heurístico.
- **SeedService:** carga idempotente de `ingredients.yaml` y `dishes.yaml` con upsert por slug, versión por hash, soft delete y `--dry-run` (F2.6). Valida estructura, cobertura y mapeo contra el catálogo (F2.7).
- **AllergenSyncService:** descarga el detalle de los productos mapeados, interpreta `nutrition_information` (`x99`, ingredientes, «puede contener») y persiste `allergen_status` y `product_allergens` (F2.4). Política fail-closed.
- **EligibilityService:** productos elegibles por ingrediente, unión de alérgenos ingrediente/producto, exclusiones por ingrediente/plato/etiqueta y disponibilidad; base de F4.2 (F2.4/F2.8).
- **PricingService:** funciones puras con `Decimal` y céntimos enteros (F3): escalado por personas/raciones, formatos comprables, necesidad neta con despensa, `plan_purchase` canónico, consumo, ticket, sobras e identidad contable. El preview de F3 y la lista de F4 comparten `plan_purchase`.
- **OptimizerService:** CP-SAT en dos etapas con presupuesto duro, demanda por paquetes `P_i`, mínimos diarios, variedad y diagnósticos de inviabilidad (F4.2-F4.4). F6 filtra solo platos `main` y añade topes blandos por fuente, misma proteína por día y pescado semanal. No abre sesiones ni persiste.
- **MenuService:** persistencia transaccional de menús, entradas y lista; recálculo con precios actuales; swap, exclude, regenerate, revalidate y «ya lo tengo»; identidades contables y rechazo por presupuesto (F4.5). F6 añade/quita acompañamientos y conserva los válidos al regenerar. La revalidación guarda ticket anterior/revalidado y delta (F5.1).
- **PriceSourceService:** `app/services/price_source.py` decide si la copia local sirve para precios actuales (`current`), solo para consultar/revalidar (`local_copy`) o no es válida (`unavailable`). Solo acepta la última sync completa de CP 22002 / almacén 4389; nunca mezcla almacenes.
- **Static frontend:** `app/static.py` monta `frontend/dist` en producción con fallback a `index.html` para rutas SPA, excluyendo `/api/*` inexistentes, recursos con extensión y documentación.
- **Operación local:** `run.ps1` resuelve `CESTA_DATA_DIR`, inicializa la base, arranca backend y frontend y limpia procesos; con `-Prod` compila y arranca solo Uvicorn sirviendo la UI. `scripts/init_db.py` crea el SQLite con sus PRAGMA; `check.ps1` agrega toda la calidad; `audit.ps1` audita dependencias; `backup_db.py`/`restore_db.py` copian y restauran con verificación; `finish-phase.ps1` cierra la fase con commit y push tras validar `check.ps1` y rechazar archivos prohibidos.

## Servicios

1. Sync de catálogo (arranque o manual).
2. Validación y carga del seed.
3. Generación de menú.
4. Recálculo de costes y lista de la compra.
5. Exportación de menú/lista.

## Frontend

Rutas:

- `/` — crear menú: personas, días y presupuesto persistidos en el perfil; genera y muestra el modal de inviabilidad.
- `/menus/:id` — menú guardado: rejilla, barra de presupuesto, estado, `stale` con delta, bloqueo, swap, «no me gusta», regeneración, revalidación al abrir y exportación.
- `/menus/:id/shopping-list` — lista agrupada, checkboxes, «ya lo tengo», totales, identidad contable e impresión A4.
- `/history` — menús guardados paginados con ticket, presupuesto, estado y enlaces.
- `/dishes` — catálogo de platos con búsqueda, filtros, detalle, «no me gusta» y coste del plato.
- `/settings` — alérgenos, exclusiones, despensa, estado del catálogo y origen de precios.
- `*` — página no encontrada.

Tooling:

- Vite 8 con alias `@/*`, tailwind plugin y proxy `/api` → `http://127.0.0.1:8000`.
- Vitest 5 + jsdom + Testing Library + MSW 3 (sin red real; `onUnhandledFrame: 'error'`).
- ESLint 10 plano + Prettier 3; TypeScript 6 con `strict` y `noUncheckedIndexedAccess`.

## Cliente Mercadona

Implementado en `app/services/mercadona_client.py`, con DTOs en `app/schemas/mercadona.py`.

- Métodos: `get_sections()` (árbol paginado) y `get_subcategory(id)` (grupos y productos).
- Sesión única de `httpx.AsyncClient`; la primera petición hace `PUT /api/postal-codes/actions/change-pc/` con `{"new_postal_code":"22002"}`.
- Fail-closed: si `x-customer-wh` no es `4389`, lanza `WarehouseUnavailableError` y no descarga catálogo.
- Todas las peticiones de catálogo llevan `wh=4389`, también las páginas siguientes.
- Reintentos con tenacity ante errores de transporte, 403, 429 y 5xx (4 intentos, backoff exponencial desde 1 s); otros 4xx no se reintentan.
- Códigos estables: `WAREHOUSE_UNAVAILABLE`, `MERCADONA_UNAVAILABLE`, `MERCADONA_HTTP_ERROR`, `MERCADONA_INVALID_RESPONSE`.
- DTOs tolerantes (`extra="ignore"`); `MercadonaProduct.id` es texto (acepta variantes como `"81649.1"`), `pack_size` admite decimales y los precios se conservan como texto para normalizarlos en F1.3; sin `raw_json`.
- `MercadonaCategoryDetail.all_products()` aplana los grupos hijos porque la API anida los productos en `categories[].products`.
- Scripts manuales: `check_mercadona.py` (una subcategoría) y `spike_catalog.py` (catálogo completo, solo métricas).
- Tests: respx + fixtures sintéticas en `backend/tests/fixtures/mercadona/`, sin red.

Contrato observado el 2026-10-25: `/api/categories/` devuelve `{count,next,previous,results}` con 26 secciones y 152 subcategorías. El detalle de subcategoría trae `products` vacío y los productos dentro de `categories[].products`; `unit_price` es el precio del paquete (pack de agua 6 × 1,5 L: 1,62 € frente a 0,18 €/L). Spike F0.5: 4.291 productos únicos, 4.543 entradas, 100 % precios parseables, 35 sin tamaño/formato, 383 con `approx_size`, 65 ids de variante, 6,37 s con concurrencia 4 y 0 fallos.

## Catálogo

- Tablas (F1.1): `categories`, `products`, `sync_runs`, `sync_category_runs`, `product_allergens`.
- `products.external_id` es TEXT único (acepta variantes como `"81649.1"`); no se persiste `raw_json`.
- Dinero en céntimos enteros; cantidades en milésimas de mg, µl o mili-unidades. `package_unit` es `g`, `ml` o `unit`; `reference_unit` es `kg`, `l`, `g`, `ml` o `unit`.
- `unit_price` de la API es el precio del paquete. Los formatos desconocidos quedan con cantidad `NULL` y no serán mapeables.
- La sync descarga 26 secciones y 152 subcategorías con concurrencia 4, reintentos 403/429/5xx y upsert por lotes. Cada subcategoría se registra en `sync_category_runs`; el estado global es `success`, `partial` o `failed`.
- Solo se marca `published=False` a productos ausentes de subcategorías descargadas correctamente. Los productos de categorías fallidas conservan la disponibilidad anterior. El barrido se hace una vez al final para que un producto duplicado siga disponible si aparece en cualquiera de las subcategorías correctas.
- El progreso se calcula con `categories_ok + categories_failed` sobre las subcategorías actuales.
- Sync real (2026-10-26): 152/152, 4.542 vistos, 4.292 únicos, 178 categorías, 7,72 s.
- UI: `CatalogStatusCard` consulta `/api/catalog/status` con TanStack Query y hace polling cada 2 s mientras `is_syncing`; el botón lanza `POST /api/catalog/sync` en segundo plano.

## Dominio y preferencias

- `ingredients.yaml`: 110 ingredientes con slug, categoría, grupo, unidad base, `grams_per_unit`, `serving_group`, `serving_size_milli`, alérgenos, etiquetas y 1-3 productos (`external_id`, prioridad y default).
- `dishes.yaml`: 60 platos con `base_servings`, `meal_types`, composición y flags derivados (`has_vegetables`, `light`, `carbs`, `protein_sources`, etiquetas). Sin pasos de cocina.
- `SeedService`: upsert por slug, hash de versión, soft delete y `dry-run`; preserva IDs de mapeos y componentes entre cargas. La carga se lanza tras la sync y también al arrancar si no toca sync.
- `AllergenSyncService`: descarga el detalle solo de los 212 productos mapeados y persiste `allergen_status` y `product_allergens`. En la primera carga real se actualizaron 210 (2 fallos transitorios reintentables), con 11-12 `unknown` y 29 `partial`. `x99` se interpreta con la lista de ingredientes; `partial`/`unknown` son fail-closed.
- `EligibilityService`: `P_i` exige producto publicado, formato fijo, precio/cantidad y, si hay alérgenos declarados, `allergen_status=known` sin alérgenos coincidentes. Si el ingrediente tiene un alérgeno declarado o `P_i` queda vacío, sus platos no son elegibles.
- Perfil único (`id=1`) con personas, días, presupuesto y alérgenos; exclusiones por ingrediente/plato/etiqueta; despensa por ingrediente en milésimas.
- API de dominio: `/api/allergens`, `/api/ingredients`, `/api/dishes`, `/api/dishes/{id}`, `/api/profile`, `/api/exclusions`, `/api/pantry`. `GET /api/dishes` acepta `q`, `meal_type`, `tag`, `light` y `only_eligible`.
- UI: Menú persiste el perfil; Platos busca, filtra y permite «no me gusta» por plato o ingrediente; Ajustes gestiona alérgenos, exclusiones, despensa y catálogo.

## Coste

Implementado en `app/services/pricing.py` (F3), con esquemas en `app/schemas/pricing.py` y endpoint en `app/api/pricing.py`.

- `scale_quantity(quantity_milli, people, base_servings)` redondea half-up por plato antes de multiplicar por sus apariciones.
- `purchasable_formats(ingredient)` exige producto publicado, precio y cantidad positivos, formato fijo (`approx_size=False`, `selling_method=0`) y la misma unidad base que el ingrediente.
- `plan_purchase(ingredient, net_need)` minimiza `Σ q × precio` sujeto a cubrir la necesidad. Usa enumeración exacta con una cota derivada del formato de menor coste unitario y un respaldo de programación dinámica para formatos con cocientes enormes. Desempata por coste, paquetes y `product_id`.
- `price_ingredient` aplica `net_need = max(0, need − pantry)`, asigna el consumo a los formatos comprados por coste unitario ascendente, valora la despensa al formato elegible más barato (o al producto por defecto si no hay compra) y calcula las sobras como residuo exacto del ticket.
- `price_basket` agrega ingredientes, reparte el consumo por aparición con el método del mayor resto y verifica la identidad global.
- `POST /api/pricing/preview` no persiste nada ni aplica filtros de alérgenos: es un preview de coste. Si no se envía despensa, usa la del perfil. Devuelve coste por plato y ración, ingredientes, paquetes y totales. `PRODUCT_UNAVAILABLE` (409) si un ingrediente no tiene producto comprable.

## Optimizador y menús

Implementado en `app/services/optimizer.py` (F4.2-F4.4) y `app/services/menu_service.py` (F4.5).

- `build_eligibility_report` resume platos elegibles por hueco, motivos por plato e ingredientes bloqueados. El optimizador solo usa `DishEligibility.eligible` y productos de `P_i`.
- Modelo CP-SAT: `x[d,s,r]`, `q[p]` y seis `violation[k]`. Coeficientes con `scale_quantity` (half-up por plato), demanda con despensa, presupuesto duro, mínimos diarios, `max_repeats`, bloqueos y un plato por día. Una pista greedy determinista y un fallback sin presupuesto evitan que presupuestos ajustados terminen en `timeout`.
- Etapa 1 minimiza violaciones de variedad; etapa 2 fija esa suma y minimiza ticket con `AddHint`. `optimal` solo con ambas etapas óptimas; `relaxed` si hay violaciones; `timeout` solo si no hay ningún menú válido tras el fallback.
- Inviabilidad: solo `budget` genera preview `infeasible` con mínimo canónico (`plan_purchase`), `minimum_is_estimate`, déficit y sugerencias. `repeats`, `minimums`, `locks` y `no_assignment` lanzan `NO_FEASIBLE_MENU`.
- `MenuService.generate` persiste el snapshot, entradas y lista; materializa `shopping_items` con `plan_purchase` sobre la necesidad agregada, limita los formatos a `P_i`, valida que la sync sea de 22002/4389 y verifica `ticket_canónico ≤ ticket_solver ≤ budget`.
- El consumo se reparte por entrada con `allocate_cents`; `used_milli` y `consumption_cents` suman exactamente el consumo del menú. `checked` se conserva por `product_id`. Los recálculos usan `menu_entry_ingredients.used_milli` como snapshot de composición; cambiar el seed de un plato no altera las cantidades del menú guardado.
- `revalidate` conserva el ticket y la lista válidos; si el recalculado supera el presupuesto, guarda el nuevo ticket en `revalidated_ticket_cents` y marca `stale` sin romper el invariante. Swap, exclude, regenerate y «ya lo tengo» sí rechazan con `BUDGET_EXCEEDED` y revierten la transacción. Tras revalidar, `previous_ticket_cents`, `revalidated_ticket_cents`, `price_delta_cents` y `revalidated_at` permiten mostrar el delta; una segunda revalidación sin cambios vuelve a `current`.
- `MenuService` valida la fuente de precios: generar exige `price_source="current"`; revalidar permite `local_copy`; cualquier producto con `last_sync_run_id` de otro almacén bloquea el recálculo con `WAREHOUSE_UNAVAILABLE`.

## F6 implementada: comidas completas y acompañamientos

- `dishes.role` (`main|complement`) y `dishes.primary_protein`, derivados de la composición al cargar el seed (migración `20261026_0006`).
- `main`: ≥0,5 raciones de proteína por persona y ≥0,5 entre verdura e hidrato. Los platos que no cumplen son `complement`.
- `menu_entries.course` (`main|complement`) con unicidad `(menu_id, day_index, slot, course)`; un principal obligatorio y como máximo un acompañamiento por hueco. Los menús históricos quedan como `course='main'`.
- El optimizador filtra solo `main`; añade topes blandos `legume_dominance`, `protein_balance`, `same_day_protein` y pescado `max(1, ceil(days × 2 / 7))`. `OPTIMIZER_VERSION = "2"`.
- `MenuService` añade y quita acompañamientos, recalcula ticket/lista/identidades y conserva los válidos en `regenerate`; los que no caben se descartan.
- API: `POST|DELETE /api/menus/{id}/entries/{main_entry_id}/complement`; `GET /api/dishes?role=main|complement`; `role` y `primary_protein` en platos, `course` en entradas.
- UI: rejilla principal + acompañamiento, diálogo de añadir/quitar, etiquetas y filtro por rol, exportación markdown con ambos cursos.

## APIs

Prefijo `/api`:

- `/health` — implementado (F0.2)
- `/catalog/status`, `/catalog/sync`, `/catalog/categories`, `/catalog/products`, `/catalog/products/{id}` — implementados (F1.5)
- `/allergens`, `/ingredients` — implementados (F2.8)
- `/dishes`, `/dishes/{id}` — implementados (F2.8)
- `/profile`, `/exclusions`, `/pantry` — implementados (F2.8)
- `/pricing/preview` — implementado (F3.5)
- `/menus/generate`, `/menus`, `/menus/{id}` — implementados (F4.6)
- `/menus/{id}/entries/{entry_id}`, `/swap`, `/exclude` — implementados (F4.6)
- `/menus/{id}/regenerate`, `/menus/{id}/revalidate` — implementados (F4.6)
- `/menus/{id}/entries/{main_entry_id}/complement` (`POST`/`DELETE`) — implementado (F6)
- `/menus/{id}/shopping-list` y `/menus/{id}/shopping-list/items/{item_id}` — implementados (F4.6)
- `/menus/{id}/export?format=markdown|csv` — implementado (F4.6)
- `/catalog/status` añade `last_valid_sync`, `price_source`, `using_local_copy`, `fallback_reason` y `price_age_hours` (F5.1)
- Menú y lista añaden `previous_ticket_cents`, `price_delta_cents` y `revalidated_at` (F5.1)

Los errores usan el sobre `{"error": {"code", "message", "details"}}`; `INVALID_HOST`
(400) cubre una cabecera `Host` no local. Los endpoints de catálogo añaden
`CATALOG_EMPTY` (503), `SYNC_IN_PROGRESS` (409), `NOT_FOUND` (404) y
`VALIDATION_ERROR` (422). Los de dominio añaden `INVALID_EXCLUSION` (422) y
`NOT_FOUND` (404). Los de menús añaden `NO_ELIGIBLE_DISHES` (422),
`NO_FEASIBLE_MENU` (422), `BUDGET_EXCEEDED` (422), `PRODUCT_UNAVAILABLE` (409),
`WAREHOUSE_UNAVAILABLE` (503) y `NOT_FOUND` (404); `reason` viaja en `details`.

## Base de Datos

SQLite en `%LOCALAPPDATA%\Cesta\cesta.db`, modo WAL, `foreign_keys=ON`, `busy_timeout=5000`.

Implementado (F0.2/F0.7/F1.1/F1.2): motor, PRAGMA por conexión, `Base` declarativa, sesión por petición, rechazo de rutas en OneDrive, `scripts/init_db.py` y migraciones Alembic con `render_as_batch=True`. `run.ps1` aplica `alembic upgrade head` antes de arrancar.

Tablas principales:

- `categories`, `products` (con `external_id` y `allergen_status`), `sync_runs`, `sync_category_runs`, `product_allergens` — implementadas (F1.1).
- `ingredients` (con `serving_group` y `serving_size_milli`), `ingredient_products` (producto único y un `is_default` por ingrediente) — implementadas (F2.1).
- `dishes` (con `role` y `primary_protein`), `dish_ingredients` (cantidad en la unidad base del ingrediente) — implementadas (F2.1 y F6).
- `profiles` (fila única `id=1`), `exclusions` (tres índices únicos parciales), `pantry_items` (`UNIQUE(profile_id, ingredient_id)`) — implementadas (F2.1).
- `menus` (con `status`, `price_status`, `timed_out`, `revalidated_ticket_cents`, `previous_ticket_cents`, `revalidated_at`, `violations`, `relaxation_codes_json` y `settings_json`), `menu_entries` (con `course`), `menu_entry_ingredients`, `shopping_items` — implementadas (F4.1, F5.1 y F6, migraciones `20261026_0003`, `20261026_0004`, `20261026_0005` y `20261026_0006`).
- Índices de entrega: `ix_menus_profile_created_at`, `ix_sync_runs_status_finished_at` e `ix_products_last_sync_run_id`.

No hay `price_snapshots` ni `raw_json` persistente en el MVP.

## Dependencias Críticas

- OR-Tools CP-SAT para el optimizador (validado en F0.6 y usado en F4.3-F4.4: 9.15.6755, `num_search_workers=1` y semilla fija).
- httpx + tenacity para la API de Mercadona (cliente implementado en F0.4).
- PyYAML para el seed de ingredientes y platos (F2).
- SQLAlchemy + Alembic para persistencia y migraciones.
- React + TanStack Query para la UI.
- SQLite como única base de datos local.
- `uv` con lockfile (`backend/uv.lock`) para reproducibilidad del backend.

## Flujo

```text
Mercadona API
    │ sync por subcategoría + detalle de productos mapeados
    ▼
SQLite (catálogo + alérgenos)
    │
    ▼
Seed de ingredientes y platos (idempotente)
    │
    ▼
Perfil + exclusiones + alérgenos + despensa
    │
    ▼
Elegibilidad fail-closed
    │
    ▼
Coste puro: plan_purchase + despensa + sobras (F3)
    │
    ▼
Optimizador CP-SAT (2 etapas) (F4.3-F4.4)
    │
    ▼
Menú + coste + lista de la compra (F4.5)
    │
    ▼
API /api/menus: generación, ajustes, lista y export (F4.6)
    │
    ▼
React UI: menú y lista de la compra (F4.7-F4.8)
    │
    ▼
Resiliencia de precios: copia local 22002/4389, stale con delta (F5.1)
    │
    ▼
Historial, impresión A4, producción en un proceso y backup (F5.2-F5.6)
    │
    ▼
Principales completos, acompañamientos opcionales y reparto de proteínas (F6)
```

## Notas

- No hay autenticación ni multiusuario en el MVP.
- No hay recetas ni pasos de cocina.
- El presupuesto es un límite duro sobre el ticket.
- La identidad `ticket + despensa = consumo + sobras` debe cumplirse.
- La app debe seguir operativa con la última copia del catálogo si la API falla, pero solo si esa copia es de 22002/4389; no se generan menús nuevos con una copia de otro almacén.
- `price_status="stale"` indica que los precios cambiaron; `previous_ticket_cents`/`revalidated_ticket_cents`/`price_delta_cents` explican el cambio. Una copia de otro almacén bloquea cualquier recálculo.
- En producción local, FastAPI sirve `frontend/dist` y las rutas del cliente caen en `index.html`; `/api/*` inexistentes y `/docs` no se enmascaran.
- `plan_purchase` es la función canónica de compra y se comparte entre preview y lista final.
- `used`/`leftover` se calculan después de resolver.
- `price_status` es independiente de `status` de generación.
- F6: todo menú nuevo tiene un `main` por hueco y como máximo un `complement`; el principal es duro y los topes de proteína son blandos. Los menús históricos se leen como `course='main'`.
- La API valida la cabecera `Host`; un host desconocido devuelve `400 INVALID_HOST`.
- La base SQLite se rechaza si `CESTA_DATA_DIR` apunta dentro de OneDrive.
