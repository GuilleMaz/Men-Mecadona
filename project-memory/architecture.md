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
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # create_app(), CORS de desarrollo, Host, prefijo /api
│   │   ├── config.py        # Settings, ruta de datos, CP 22002 / almacén 4389
│   │   ├── db.py            # motor SQLite, PRAGMA, Base, sesiones
│   │   ├── security.py      # allowlist de Host local
│   │   ├── api/             # routers (health.py)
│   │   ├── schemas/         # health.py, mercadona.py (DTOs de la API)
│   │   ├── models/          # pendiente F1
│   │   ├── services/        # mercadona_client.py (pricing/optimizer/menu pendientes)
│   │   └── data/            # pendiente F2 (ingredients.yaml, dishes.yaml)
│   └── tests/               # API, config, db, seguridad y cliente Mercadona + fixtures
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
│       │   ├── layout/AppLayout.tsx
│       │   ├── layout/BackendStatus.tsx
│       │   └── ui/          # button, card, input, label
│       ├── pages/           # MenuPage, DishesPage, SettingsPage, NotFoundPage
│       ├── lib/utils.ts
│       └── test/            # setup, servidor MSW con /api/health, render-app
├── scripts/                 # check_mercadona.py, spike_catalog.py, spike_ortools.py, init_db.py
├── run.ps1                  # backend + frontend, SQLite fuera de OneDrive
├── check.ps1                # lint + tipos + tests + build
└── finish-phase.ps1         # calidad + commit + push a GitHub
```

`backend/app` es un paquete plano (no se distribuye): `uv` usa `package = false` y
pytest resuelve `app` con `pythonpath = ["."]` desde `backend/`.

## Componentes

- **Frontend React:** layout en español con navegación Menú / Platos / Ajustes, formulario placeholder de personas/días/presupuesto, páginas de Platos y Ajustes e indicador de estado de la API (`BackendStatus` con TanStack Query). Implementado el esqueleto (F0.3/F0.10); la lógica de menú llega en F4.
- **FastAPI:** API REST, validación Pydantic, orquestación de servicios. Implementado el esqueleto, `/api/health` y la validación de `Host`.
- **Configuración (`app/config.py`):** `Settings` con `APP_ENV`, `SYNC_ON_STARTUP`, `OPTIMIZER_TIME_LIMIT_SECONDS` y `CESTA_DATA_DIR` opcional absoluto. Rechaza rutas dentro de OneDrive. Constantes `POSTAL_CODE="22002"`, `EXPECTED_WAREHOUSE="4389"` y `LOCAL_HOSTS`.
- **Seguridad (`app/security.py`):** `HostValidationMiddleware` acepta solo `127.0.0.1`, `localhost` y `::1`; el resto devuelve `400 INVALID_HOST`.
- **Persistencia (`app/db.py`):** motor SQLite con `foreign_keys=ON`, WAL y `busy_timeout=5000`; `Base` declarativa y sesión por petición.
- **MercadonaClient:** cliente asíncrono implementado (F0.4); fija CP 22002, valida almacén 4389, descarga secciones y subcategorías. Ver sección propia y el informe del spike en `decisions.md`.
- **CatalogSyncService:** sync por subcategoría, estado parcial, disponibilidad y errores. Pendiente (F1).
- **PricingService:** unidades base, necesidad neta, paquetes, ticket, consumo, despensa y sobras. Pendiente (F3).
- **OptimizerService:** CP-SAT en dos etapas con presupuesto duro. Pendiente (F4).
- **MenuService:** persistencia de menús, bloqueos, cambios, regeneración y lista. Pendiente (F4).
- **SeedService:** carga idempotente y validación de ingredientes, productos y platos. Pendiente (F2).
- **Operación local:** `run.ps1` resuelve `CESTA_DATA_DIR`, inicializa la base, arranca backend y frontend y limpia procesos; `scripts/init_db.py` crea el SQLite con sus PRAGMA; `check.ps1` agrega toda la calidad; `finish-phase.ps1` cierra la fase con commit y push tras validar `check.ps1` y rechazar archivos prohibidos.

## Servicios

1. Sync de catálogo (arranque o manual).
2. Validación y carga del seed.
3. Generación de menú.
4. Recálculo de costes y lista de la compra.
5. Exportación de menú/lista.

## Frontend

Rutas:

- `/` — crear menú (formulario placeholder; generación real en F4).
- `/dishes` — catálogo de platos (F2).
- `/settings` — exclusiones, alérgenos, despensa y sync (F1/F2).
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

## APIs

Prefijo `/api`:

- `/health` — implementado (F0.2)
- `/catalog/status`, `/catalog/sync`, `/catalog/categories`, `/catalog/products`
- `/allergens`
- `/dishes`
- `/profile`, `/exclusions`, `/pantry`
- `/pricing/preview`
- `/menus/generate`, `/menus`, `/menus/{id}`
- `/menus/{id}/entries/{entry_id}`, `/swap`, `/exclude`
- `/menus/{id}/regenerate`
- `/menus/{id}/revalidate`
- `/menus/{id}/shopping-list`
- `/menus/{id}/export`

Los errores usan el sobre `{"error": {"code", "message", "details"}}`; `INVALID_HOST`
(400) cubre una cabecera `Host` no local.

## Base de Datos

SQLite en `%LOCALAPPDATA%\Cesta\cesta.db`, modo WAL, `foreign_keys=ON`, `busy_timeout=5000`.

Implementado (F0.2/F0.7): motor, PRAGMA por conexión, `Base` declarativa, sesión por petición, rechazo de rutas en OneDrive y `scripts/init_db.py` para crear el archivo. Las tablas y migraciones llegan en F1.1/F1.2.

Tablas principales:

- `categories`, `products` (con `external_id` y `allergen_status`), `sync_runs`, `sync_category_runs`, `product_allergens`
- `ingredients` (con `serving_group` y `serving_size_milli`), `ingredient_products`
- `dishes`, `dish_ingredients`
- `profiles`, `exclusions`, `pantry_items`
- `menus` (con `status`, `price_status`, `timed_out`), `menu_entries`, `menu_entry_ingredients`, `shopping_items`

No hay `price_snapshots` ni `raw_json` persistente en el MVP.

## Dependencias Críticas

- OR-Tools CP-SAT para el optimizador (validado en F0.6: 9.15.6755 resuelve el toy de 28 huecos en 3,46-3,47 s con un worker).
- httpx + tenacity para la API de Mercadona (cliente implementado en F0.4).
- SQLAlchemy + Alembic para persistencia y migraciones.
- React + TanStack Query para la UI.
- SQLite como única base de datos local.
- `uv` con lockfile (`backend/uv.lock`) para reproducibilidad del backend.

## Flujo

```text
Mercadona API
    │ sync por subcategoría
    ▼
SQLite (catálogo)
    │
    ▼
Seed de platos e ingredientes
    │
    ▼
Perfil + exclusiones + alérgenos + despensa
    │
    ▼
Optimizador CP-SAT (2 etapas)
    │
    ▼
Menú + coste + lista de la compra
    │
    ▼
React UI
```

## Notas

- No hay autenticación ni multiusuario en el MVP.
- No hay recetas ni pasos de cocina.
- El presupuesto es un límite duro sobre el ticket.
- La identidad `ticket + despensa = consumo + sobras` debe cumplirse.
- La app debe seguir operativa con la última copia del catálogo si la API falla, pero solo si esa copia es de 22002/4389; no se generan menús nuevos con una copia de otro almacén.
- `plan_purchase` es la función canónica de compra y se comparte entre preview y lista final.
- `used`/`leftover` se calculan después de resolver.
- `price_status` es independiente de `status` de generación.
- La API valida la cabecera `Host`; un host desconocido devuelve `400 INVALID_HOST`.
- La base SQLite se rechaza si `CESTA_DATA_DIR` apunta dentro de OneDrive.
