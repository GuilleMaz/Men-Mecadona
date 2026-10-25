# Architecture

## Estructura

```text
MERCADONA/
├── PLAN.md
├── TASKS.md
├── AGENTS.md
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
│   │   ├── main.py          # create_app(), CORS de desarrollo, prefijo /api
│   │   ├── config.py        # Settings, ruta de datos, CP 22002 / almacén 4389
│   │   ├── db.py            # motor SQLite, PRAGMA, Base, sesiones
│   │   ├── api/             # routers (health.py)
│   │   ├── schemas/         # esquemas Pydantic (health.py)
│   │   ├── models/          # pendiente F1
│   │   ├── services/        # pendiente F0.4+
│   │   └── data/            # pendiente F2 (ingredients.yaml, dishes.yaml)
│   └── tests/
├── frontend/                # reservado; se inicializa en F0.3
├── scripts/                 # reservado; primer script en F0.5
├── run.ps1                  # pendiente F0.7
└── check.ps1                # pendiente F0.9
```

`backend/app` es un paquete plano (no se distribuye): `uv` usa `package = false` y
pytest resuelve `app` con `pythonpath = ["."]` desde `backend/`.

## Componentes

- **Frontend React:** formulario de creación, rejilla de menú, lista de la compra, catálogo de platos y ajustes. Pendiente (F0.3).
- **FastAPI:** API REST, validación Pydantic, orquestación de servicios. Implementado el esqueleto y `/api/health`.
- **Configuración (`app/config.py`):** `Settings` con `APP_ENV`, `SYNC_ON_STARTUP`, `OPTIMIZER_TIME_LIMIT_SECONDS` y `CESTA_DATA_DIR` opcional absoluto. Constantes `POSTAL_CODE="22002"` y `EXPECTED_WAREHOUSE="4389"`.
- **Persistencia (`app/db.py`):** motor SQLite con `foreign_keys=ON`, WAL y `busy_timeout=5000`; `Base` declarativa y sesión por petición.
- **MercadonaClient:** fija CP 22002, obtiene almacén 4389, descarga catálogo y normaliza respuestas. Pendiente (F0.4).
- **CatalogSyncService:** sync por subcategoría, estado parcial, disponibilidad y errores. Pendiente (F1).
- **PricingService:** unidades base, necesidad neta, paquetes, ticket, consumo, despensa y sobras. Pendiente (F3).
- **OptimizerService:** CP-SAT en dos etapas con presupuesto duro. Pendiente (F4).
- **MenuService:** persistencia de menús, bloqueos, cambios, regeneración y lista. Pendiente (F4).
- **SeedService:** carga idempotente y validación de ingredientes, productos y platos. Pendiente (F2).

## Servicios

1. Sync de catálogo (arranque o manual).
2. Validación y carga del seed.
3. Generación de menú.
4. Recálculo de costes y lista de la compra.
5. Exportación de menú/lista.

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

## Base de Datos

SQLite en `%LOCALAPPDATA%\Cesta\cesta.db`, modo WAL, `foreign_keys=ON`, `busy_timeout=5000`.

Implementado (F0.2): motor, PRAGMA por conexión, `Base` declarativa y sesión por petición. Las tablas y migraciones llegan en F1.1/F1.2.

Tablas principales:

- `categories`, `products` (con `external_id` y `allergen_status`), `sync_runs`, `sync_category_runs`, `product_allergens`
- `ingredients` (con `serving_group` y `serving_size_milli`), `ingredient_products`
- `dishes`, `dish_ingredients`
- `profiles`, `exclusions`, `pantry_items`
- `menus` (con `status`, `price_status`, `timed_out`), `menu_entries`, `menu_entry_ingredients`, `shopping_items`

No hay `price_snapshots` ni `raw_json` persistente en el MVP.

## Dependencias Críticas

- OR-Tools CP-SAT para el optimizador (verificado: 9.15 instala en Windows/Python 3.13; spike F0.6 pendiente).
- httpx para la API de Mercadona.
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
