# Changelog

## 2026-10-26 — F2: ingredientes, platos, alérgenos y preferencias

### Cambios

- Backend: modelos `Ingredient`, `IngredientProduct`, `Dish`, `DishIngredient`,
  `Profile`, `Exclusion` y `PantryItem` con CHECKs, FKs, índices únicos parciales
  y `UNIQUE(product_id)`; migración `20261026_0002`.
- Seed: `backend/app/data/ingredients.yaml` (110 ingredientes, 212 mapeos a
  productos) y `dishes.yaml` (60 platos sin pasos, 30 de comida, 45 de cena, 19
  cenas ligeras). Flags y etiquetas derivados de la composición.
- `SeedService` idempotente con `seed_version` por hash, soft delete, upsert de
  mapeos y componentes, y `dry-run`. Scripts `load_seed.py` y
  `validate_seed.py`.
- Alérgenos: `MercadonaClient.get_product`, DTOs de detalle, parser HTML con
  `x99`, ingredientes y «puede contener», `AllergenSyncService` fail-closed y
  enriquecimiento de los 212 productos mapeados reales (12 `unknown`, 29
  `partial`, 0 fallos). Script `sync_allergens.py`.
- Elegibilidad reutilizable: `app/services/eligibility.py` con `P_i`, unión
  ingrediente/producto, exclusiones y motivos estables. Base de F4.2.
- API: `/api/allergens`, `/api/ingredients`, `/api/dishes`,
  `/api/dishes/{id}`, `/api/profile`, `/api/exclusions`, `/api/pantry`.
  Filtros `q`, `meal_type`, `tag`, `light`, `only_eligible`; perfil con
  `allergen_codes` opcional (si se omite, se conserva); despensa transaccional.
- Arranque: la sync recarga el seed y enriquece alérgenos al terminar; si no
  toca sync, el seed se carga en segundo plano. `run.ps1` sigue aplicando
  migraciones antes de arrancar.
- Frontend: formulario de menú persistente; catálogo de platos con búsqueda,
  momento, etiqueta, ligero, visibilidad de no elegibles, detalle y «no me
  gusta» por plato o ingrediente; Ajustes con alérgenos, exclusiones y despensa.
  MSW con handlers de dominio.
- Documentación: README raíz/backend/frontend, `TASKS.md`, `PLAN.md` y
  `project-memory/`.

### Verificación

- `uv run ruff check .`, `ruff format --check .`, `mypy app`: OK.
- `uv run pytest`: 161 tests en verde, sin red (41 nuevos).
- `npm run lint`, `format:check`, `typecheck`, `test` (26 tests, 10 nuevos) y
  `build`: OK.
- `uv run alembic upgrade head` sobre base nueva: 12 tablas + `alembic_version`;
  `alembic check`: sin deriva.
- Seed contra copia del catálogo real: 110 ingredientes, 212 mapeos, 60 platos;
  dos cargas consecutivas conservan IDs; `validate_seed.py` → OK (0 avisos).
- Sync real de alérgenos: 212 productos mapeados; 212 actualizados en la prueba
  aislada y 210 en la base real (2 fallos transitorios reintentables); 11-12
  `unknown`, 29 `partial`.
- API real: `/api/dishes` devuelve 60 platos; con gluten declarado y alérgenos
  enriquecidos, `only_eligible=true` devuelve 7 platos (fail-closed).
- UI: tests de menú, catálogo, detalle, exclusiones, alérgenos y despensa.

### Archivos

- `backend/app/models/ingredients.py`, `backend/app/models/dishes.py`,
  `backend/app/models/profile.py`, `backend/app/models/__init__.py`
- `backend/alembic/versions/20261026_0002_domain.py`
- `backend/app/data/ingredients.yaml`, `backend/app/data/dishes.yaml`
- `backend/app/schemas/seed.py`, `backend/app/schemas/domain.py`,
  `backend/app/schemas/mercadona.py`
- `backend/app/services/seed.py`, `backend/app/services/allergen_sync.py`,
  `backend/app/services/eligibility.py`, `backend/app/services/mercadona_client.py`
- `backend/app/api/domain.py`, `backend/app/main.py`, `backend/app/allergens.py`,
  `backend/app/models/catalog.py` (relación de alérgenos)
- `backend/tests/domain_fixtures.py`, `backend/tests/test_seed.py`,
  `backend/tests/test_allergens.py`, `backend/tests/test_domain_api.py`,
  `backend/tests/test_domain_migrations.py`, `backend/tests/test_catalog_migrations.py`
- `frontend/src/lib/domain.ts`, `frontend/src/lib/labels.ts`,
  `frontend/src/pages/MenuPage.tsx`, `frontend/src/pages/DishesPage.tsx`,
  `frontend/src/pages/SettingsPage.tsx`,
  `frontend/src/components/preferences/**`, `frontend/src/test/server.ts`
- `scripts/load_seed.py`, `scripts/validate_seed.py`, `scripts/sync_allergens.py`,
  `scripts/sync_catalog.py`, `backend/pyproject.toml`, `backend/uv.lock`
- `README.md`, `backend/README.md`, `frontend/README.md`, `PLAN.md`, `TASKS.md`
- `project-memory/**`

### Motivo

- Cerrar F2 con el catálogo de platos validado, alérgenos fail-closed y el
  usuario configurable antes de construir el motor de costes de F3.

## 2026-10-26 — F1: catálogo y sincronización

### Cambios

- Backend: modelos `Category`, `Product`, `SyncRun`, `SyncCategoryRun` y
  `ProductAllergen` con CHECKs, FKs, índices y `UtcDateTime`; lista canónica de
  alérgenos en `app/allergens.py`.
- Alembic: `alembic.ini`, `env.py`, plantilla y migración inicial
  `20261026_0001`; URL desde `Settings`, `render_as_batch=True` y WAL.
- Normalizador puro `catalog_normalizer.py`: precios con `Decimal` a céntimos,
  cantidades a milésimas (`g`/`ml`/`unit`), packs, precio de referencia,
  mostrador/peso variable, formatos desconocidos e `is_food` heurístico.
- Sync `catalog_sync.py`: concurrencia 4, progreso por subcategoría, upsert
  idempotente por `external_id`, estados `success`/`partial`/`failed`, barrido
  final de disponibilidad para productos duplicados entre subcategorías, lock de
  proceso, recuperación de syncs interrumpidas y refresh de arranque a las 24 h.
- API `/api/catalog/status`, `/api/catalog/sync`, `/api/catalog/categories`,
  `/api/catalog/products` y `/api/catalog/products/{id}` con paginación,
  filtro por subárbol, `only_available` y errores homogéneos. Adaptadores de
  errores de dominio, validación y HTTP.
- `create_app` admite `session_factory` para tests, monta el lifespan de sync y
  no bloquea el startup. `run.ps1` aplica `alembic upgrade head`.
- Script `scripts/sync_catalog.py` para sincronizar el catálogo real y mostrar el
  resumen.
- Frontend: `lib/catalog.ts`, `CatalogStatusCard` en Ajustes con estado, conteos,
  CP/almacén, fecha de precios, errores, barra de progreso, polling cada 2 s y
  botón «Actualizar catálogo»; handlers MSW por defecto.
- Documentación: README raíz, backend y frontend; `TASKS.md` y `project-memory/`.

### Verificación

- `uv run ruff check .`, `ruff format --check .` y `mypy app`: OK.
- `uv run pytest`: 120 tests en verde, sin red.
- `uv run ruff check` y `ruff format --check` sobre `scripts/`: OK.
- `npm run lint`, `format:check`, `typecheck`, `test` (16 tests) y `build`: OK.
- `uv run alembic upgrade head` sobre base vacía: 5 tablas + `alembic_version`;
  `uv run alembic check`: sin deriva.
- Sync real: 152/152 subcategorías, 4.540 productos vistos, 4.288 únicos,
  178 categorías, 7,74 s, `success`, CP 22002 / almacén 4389.
- Arranque con base vacía: `/api/catalog/status` responde en 0,46 s con
  `is_syncing=true` (la UI no se bloquea) y la sync termina en 8,28 s con 4.288
  productos.
- API real: `product_count=4288`, 26 secciones, 152 subcategorías,
  `q=aceite` devuelve 69 resultados; precios y cantidades en enteros.

### Archivos

- `backend/app/models/**`, `backend/app/allergens.py`
- `backend/alembic.ini`, `backend/alembic/**`
- `backend/app/services/catalog_normalizer.py`, `backend/app/services/catalog_sync.py`
- `backend/app/schemas/catalog.py`, `backend/app/schemas/mercadona.py`
- `backend/app/api/catalog.py`, `backend/app/api/errors.py`, `backend/app/main.py`
- `backend/app/db.py`, `backend/pyproject.toml`
- `backend/tests/**`
- `frontend/src/lib/catalog.ts`, `frontend/src/components/catalog/**`
- `frontend/src/pages/SettingsPage.tsx`, `frontend/src/test/server.ts`
- `scripts/sync_catalog.py`, `run.ps1`, `README.md`, `backend/README.md`, `frontend/README.md`
- `TASKS.md`, `project-memory/**`

### Motivo

- Cerrar F1 con el catálogo real persistido, la sync parcial robusta, la búsqueda
  operativa y la UI de estado antes de construir ingredientes y platos en F2.

## 2026-10-26 — Pipeline de cierre de fase

### Cambios

- `finish-phase.ps1`: gate único de cierre. Ejecuta `check.ps1`, rechaza archivos
  prohibidos, crea el commit `FASE: resumen` y hace push al remoto.
- `AGENTS.md`: flujo de trabajo, comandos, DoD y prohibiciones actualizados para
  exigir commit y push al cerrar cada fase.
- `TASKS.md`: convención de cierre y uso obligatorio de `finish-phase.ps1`.
- `README.md`: sección de cierre de fase.
- `project-memory/decisions.md`: decisión y alternativas del pipeline.

### Verificación

- Primera ejecución sobre F0: `check.ps1` en verde (50 tests de backend, 10 de frontend y build), commit `be7e149` y push a `origin/main`.
- `finish-phase.ps1` rechaza `Phase` inválida y remotos inexistentes antes de tocar el árbol de trabajo.

### Archivos

- `finish-phase.ps1`
- `AGENTS.md`, `TASKS.md`, `README.md`
- `project-memory/**`

### Motivo

- Evitar que una fase quede sin commit o sin subir a GitHub y convertir la calidad
  y la trazabilidad en un paso obligatorio del flujo.

## 2026-10-26 — F0.6-F0.10: cierre de F0

### Cambios

- `scripts/spike_ortools.py`: modelo toy CP-SAT con 28 huecos, 60 platos, 120 ingredientes y 240 paquetes; demanda dependiente de la selección, despensa, presupuesto duro, mínimos diarios, dos bloqueos y variedad en dos etapas. Fija `num_search_workers=1` y semilla 42, valida la solución y mide tiempos.
- `run.ps1`: resuelve `CESTA_DATA_DIR` (por defecto `%LOCALAPPDATA%\Cesta`), rechaza OneDrive, inicializa la base, arranca backend en `127.0.0.1:8000`, espera salud, arranca Vite en `localhost:5173` y limpia el árbol de procesos al salir.
- `scripts/init_db.py`: crea el archivo SQLite y comprueba WAL, `foreign_keys=ON` y `busy_timeout=5000` fuera de OneDrive.
- `backend/app/config.py`: rechaza `CESTA_DATA_DIR` dentro de OneDrive y expone la allowlist de hosts locales.
- `backend/app/security.py` y `backend/app/main.py`: `HostValidationMiddleware` para `127.0.0.1`, `localhost` y `::1`, con `400 INVALID_HOST` homogéneo.
- `check.ps1`: lint, formato, tipos, tests y build de backend, scripts y frontend en un comando.
- Frontend: `BackendStatus` consulta `/api/health` con TanStack Query y muestra «API conectada»/«API no disponible»; handler MSW por defecto y tests de éxito, error y respuesta inválida.
- Documentación: `README.md`, `SECURITY.md`, actualización de `backend/README.md` y `frontend/README.md`, y código `INVALID_HOST` en `PLAN.md` §10.4.
- `scripts/spike_catalog.py` se reformatea con Ruff (sin cambios funcionales) para que `check.ps1` valide también los scripts.
- Tests nuevos: 22 de seguridad/Host, 2 de configuración de OneDrive/allowed hosts y 4 de frontend de estado de la API.

### Verificación

- `.\check.ps1`: Ruff, formato, mypy, 50 tests de backend, ESLint, Prettier, TypeScript, 10 tests de frontend y build: todo en verde (28,0 s).
- Spike OR-Tools, 3 repeticiones: etapa 1 `OPTIMAL` con 0 violaciones en 0,28-0,29 s; etapa 2 `FEASIBLE` con ticket 333,18 € (presupuesto 358,16 €) en 3,00 s; total 3,46-3,47 s; validación completa OK. DoD <10 s: APTO.
- `.\run.ps1`: UI 200, `/api/health` directo y a través del proxy de Vite 200; base creada en `C:\Users\guill\AppData\Local\Cesta\cesta.db` con WAL, `foreign_keys=1` y `busy_timeout=5000`.
- `.\run.ps1` detiene backend y frontend sin dejar puertos 8000/5173 escuchando.

### Archivos

- `run.ps1`, `check.ps1`, `README.md`, `SECURITY.md`, `.env.example`
- `scripts/init_db.py`, `scripts/spike_ortools.py`
- `backend/app/config.py`, `backend/app/main.py`, `backend/app/security.py`
- `backend/tests/test_config.py`, `backend/tests/test_cors.py`, `backend/tests/test_health.py`, `backend/tests/test_security.py`
- `frontend/src/components/layout/AppLayout.tsx`, `frontend/src/components/layout/BackendStatus.tsx`, `frontend/src/components/layout/BackendStatus.test.tsx`, `frontend/src/App.test.tsx`, `frontend/src/pages/MenuPage.tsx`, `frontend/src/pages/MenuPage.test.tsx`, `frontend/src/test/server.ts`
- `backend/README.md`, `frontend/README.md`, `PLAN.md`
- `AGENTS.md`, `TASKS.md`, `project-memory/**`

### Motivo

- Cerrar F0 con OR-Tools validado, arranque local reproducible, seguridad local básica, scripts de calidad y smoke test de `/api/health` antes de iniciar F1.

## 2026-10-25 — F0.5: spike del catálogo

### Cambios

- `scripts/spike_catalog.py`: descarga las 152 subcategorías con concurrencia 4 y calcula métricas sin persistir catálogo ni `raw_json`.
- Corregido el contrato del cliente tras el spike: `pack_size` pasa a `float | None` (packs con unidades de 1,5 L) y `MercadonaProduct.id` a texto con `coerce_numbers_to_str` (ids de variante como `"81649.1"`).
- El cliente trata también el 403 como transitorio (WAF de Mercadona) además de 429/5xx: 4 intentos con backoff exponencial desde 1 s.
- Inicialización de sesión protegida con `asyncio.Lock`: las descargas concurrentes comparten un único PUT de CP.
- Tests nuevos: pack decimal, id de variante, 403 transitorio y sesión única bajo concurrencia; 26 tests en total.
- Informe completo del spike en `project-memory/decisions.md`.

### Resultado del spike

- 26 secciones, 152/152 subcategorías, 0 fallos.
- 4.543 entradas y 4.291 productos únicos (referencia ~4.327; −36, −0,8 %).
- 100 % de precios parseables, 0 sin precio y 0 no publicados.
- 35 productos sin tamaño/formato, 383 con `approx_size` y 65 ids de variante.
- 6,37 s con concurrencia 4.

### Verificación

- Ruff, mypy strict (app y script) y 26 tests en verde.
- Spike reproducible: `cd backend; uv run python ..\scripts\spike_catalog.py` → APTO.

### Archivos

- `scripts/spike_catalog.py`
- `backend/app/schemas/mercadona.py`
- `backend/app/services/mercadona_client.py`
- `backend/tests/test_mercadona_client.py`
- `TASKS.md`
- `project-memory/**`

### Motivo

- Validar el catálogo completo y fijar el contrato real antes de F1.

## 2026-10-25 — F0.4: cliente Mercadona mínimo

### Cambios

- `MercadonaClient` asíncrono con httpx: fija el CP 22002, valida `x-customer-wh=4389` y reutiliza cookies de sesión.
- Reintentos con tenacity ante transporte, 429 y 5xx (3 intentos; F0.5 amplió a 403 y 4 intentos); errores de dominio con códigos `WAREHOUSE_UNAVAILABLE`, `MERCADONA_UNAVAILABLE`, `MERCADONA_HTTP_ERROR` y `MERCADONA_INVALID_RESPONSE`.
- `get_sections()` sigue la paginación de `/api/categories/`; `get_subcategory(id)` descarga grupos y productos. `wh=4389` se mantiene en todas las páginas.
- DTOs Pydantic tolerantes (`extra="ignore"`) en `app/schemas/mercadona.py`; precios como texto para normalizar en F1.3; sin `raw_json`.
- Fixtures sintéticas mínimas: 1 sección, 2 subcategorías y 3 productos (incluido un pack 6 × 125 g y un grupo vacío).
- 8 tests nuevos con respx: flujo completo, paginación, almacén incorrecto/ausente, reintentos agotados, 404 y respuesta inválida.
- Script `scripts/check_mercadona.py` y sección de uso en `backend/README.md`.

### Verificación

- `uv run ruff check .` y `uv run ruff format --check .`: OK.
- `uv run mypy app`: OK (strict, 11 archivos).
- `uv run pytest`: 22 passed.
- Script real contra Mercadona: 26 secciones, 152 subcategorías, almacén 4389, CP 22002, 38 productos en la subcategoría 112 y producto parseado `Aceite de oliva 0,4º Hacendado` (17,25 € el paquete de 5 L).

### Archivos

- `backend/app/schemas/mercadona.py`
- `backend/app/services/{__init__,mercadona_client}.py`
- `backend/tests/test_mercadona_client.py`
- `backend/tests/fixtures/mercadona/{categories,subcategory_112}.json`
- `backend/README.md`
- `scripts/check_mercadona.py`
- `TASKS.md`
- `project-memory/**`

### Motivo

- Validar el acceso a Mercadona y el almacén 4389 antes de diseñar el catálogo persistente y la sync de F1.

## 2026-10-25 — F0.3: frontend mínimo y tooling

### Cambios

- Vite 8 + React 19 + TypeScript 6 estricto (`strict`, `noUncheckedIndexedAccess`) con alias `@/*`.
- Tailwind CSS 4 mediante `@tailwindcss/vite` y tema shadcn/ui en `src/index.css` (variables oklch, primario verde).
- shadcn/ui por copia: `components.json` (`new-york`), `lib/utils.ts` y componentes `button`, `card`, `input` y `label` sobre Radix.
- TanStack Query 5, React Router 8, React Hook Form 7 + Zod 4 (resolvers 5) y Lucide.
- Layout base en español con navegación Menú / Platos / Ajustes, foco visible y pie con aviso legal.
- Formulario placeholder de personas (1-10), días (1-14) y presupuesto (€) con validación Zod en español y resumen no persistente.
- Páginas de Platos y Ajustes como placeholders explícitos; 404 con vuelta al menú.
- Vitest 5 + jsdom + Testing Library + MSW 3 (`onUnhandledFrame: 'error'`), con limpieza y servidor sin handlers.
- ESLint 10 plano (typescript-eslint, react-hooks, react-refresh, Prettier) y scripts `lint`, `format`, `format:check`, `test`, `typecheck`.
- Proxy de Vite `/api` → `http://127.0.0.1:8000` para desarrollo.
- `components.json` normalizado a `new-york` porque el CLI de shadcn no es viable sin TTY (ver `decisions.md`).

### Verificación

- `npm run lint`: sin errores ni avisos.
- `npm run format:check`: OK.
- `npm run typecheck`: OK con TypeScript 6 estricto.
- `npm run test`: 6 tests en 2 archivos.
- `npm run build`: OK (2169 módulos; JS 137 kB gzip, CSS 3,9 kB gzip).
- `npm run dev`: `http://localhost:5173` responde 200 con título «Cesta — Menús de comida y cena» y `#root`.

### Archivos

- `frontend/**`
- `TASKS.md`
- `project-memory/**`

### Motivo

- Cumplir el DoD de F0.3 (UI mínima en español, tooling y tests) antes de integrar el catálogo de Mercadona.

## 2026-10-25 — F0.1 y F0.2: estructura y backend mínimo

### Cambios

- Creada la estructura base: `backend/` con código, y `frontend/` y `scripts/` reservados con `.gitkeep`.
- `.gitignore` para Python, Node, SQLite, `.env`, build y `node_modules`. `uv.lock` se versiona a propósito.
- `.gitattributes` con `eol=lf` para evitar ruido de finales de línea entre equipos.
- `.env.example` con `APP_ENV`, `SYNC_ON_STARTUP`, `OPTIMIZER_TIME_LIMIT_SECONDS=8` y `CESTA_DATA_DIR` opcional y absoluto, comentado.
- Backend inicializado con `uv` y Python 3.13: FastAPI, Uvicorn, Pydantic v2, pydantic-settings, SQLAlchemy 2, Alembic, httpx, tenacity y OR-Tools; dev: pytest, pytest-asyncio, respx, Ruff y mypy.
- `app/main.py` con `create_app()`, CORS solo en desarrollo para `http://localhost:5173` y routers bajo `/api`.
- `app/config.py` con `Settings` validado: `CESTA_DATA_DIR` absoluto o `%LOCALAPPDATA%\Cesta`; constantes `POSTAL_CODE="22002"` y `EXPECTED_WAREHOUSE="4389"`.
- `app/db.py` con motor SQLite, `Base` declarativa, sesión por petición y PRAGMA `foreign_keys=ON`, WAL y `busy_timeout=5000`.
- `GET /api/health` → `{"status":"ok"}` con esquema `HealthResponse`.
- 14 tests: health y OpenAPI, CORS permitido/denegado, producción sin CORS, configuración y PRAGMA de SQLite.
- Repositorio git inicializado en `main` con remoto `Men-Mecadona`.

### Verificación

- `uv run ruff check .` y `uv run ruff format --check .`: OK.
- `uv run mypy app`: OK (strict).
- `uv run pytest`: 14 passed.
- `python -m uvicorn app.main:app`: `GET /api/health` → 200 `{"status":"ok"}`.
- OR-Tools 9.15 instalado en Windows/Python 3.13 (el spike F0.6 sigue pendiente).

### Archivos

- `.gitignore`, `.gitattributes`, `.env.example`
- `backend/pyproject.toml`, `backend/uv.lock`, `backend/.python-version`, `backend/README.md`
- `backend/app/**`, `backend/tests/**`
- `frontend/.gitkeep`, `scripts/.gitkeep`
- `TASKS.md`, `project-memory/**`

### Motivo

- Cumplir el DoD de F0.1 y F0.2 (árbol reproducible, backend ejecutable y calidad en verde) antes del frontend y los spikes.

## 2026-10-25 — Verificación final APTO

### Cambios

- Auditoría final estrecha sobre los seis bloqueantes: APTO.
- Confirmado que la demanda CP-SAT depende de `x`, `used`/`leftover` son post-cálculo, los alérgenos son fail-closed, la variedad está operacionalizada, `plan_purchase` es único y el contrato de estados está separado.
- Confirmado que no quedan referencias rotas a F0.8/OR-Tools, CRUD de exclusiones, variables `used`/`leftover`, `MERCADONA_POSTAL_CODE`, `CESTA_DATA_DIR=%LOCALAPPDATA%` ni `id:` en el YAML de platos.

### Archivos

- `PLAN.md`
- `TASKS.md`
- `AGENTS.md`
- `project-memory/*`

### Motivo

- Cerrar la fase de planificación antes de iniciar F0.

## 2026-10-25 — Cierre de contratos tras auditoría final

### Cambios

- Corregida la demanda del CP-SAT para que dependa de `x`: `coef[r,i]` por plato y `need_i(x)` agregada.
- `used` y `leftover` pasan a ser post-cálculo determinista, no variables del solver.
- Alérgenos fail-closed representables: `allergen_status`, lista canónica, `P_i` filtrado, unión ingrediente/producto y producto de respaldo.
- Operacionalizados los mínimos diarios por persona y las reglas de variedad con métricas, umbrales y violaciones de peso 1.
- Añadido `plan_purchase` canónico compartido por preview y lista final.
- Separados `status` de generación, `price_status`, `timed_out` e `is_preview`.
- Añadidas causas de inviabilidad (`budget`, `repeats`, `minimums`, `locks`, `no_assignment`) y `minimum_is_estimate`.
- La copia local solo se usa si es de 22002/4389 y solo para consultar; no genera menús nuevos.
- Aclarado `CESTA_DATA_DIR` absoluto y eliminado el CP configurable por entorno.
- Añadidos tests de RF-17, alérgenos bajo presupuesto, `preview==shopping_list`, `base_servings` distintos, exportación/CSV, privacidad y accesibilidad.
- Corregidas referencias menores: F0.6, CRUD de exclusiones, bloqueo/desbloqueo, paginación, `slug` y `APP_ENV`.

### Archivos

- `PLAN.md`
- `TASKS.md`
- `AGENTS.md`
- `project-memory/project-overview.md`
- `project-memory/architecture.md`
- `project-memory/decisions.md`
- `project-memory/changelog.md`
- `project-memory/next-steps.md`

### Motivo

- Cerrar los bloqueantes de especificación detectados por la auditoría final antes de implementar F2/F3/F4.
- Dejar contratos implementables y verificables.

## 2026-10-25 — Consolidación tras auditoría

### Cambios

- Reescritura de `PLAN.md` para cerrar los contratos de presupuesto, coste, alérgenos, unidades y optimizador.
- Reescritura de `TASKS.md` con fases accionables, spikes tempranos y tareas que faltaban: OR-Tools, carga del seed, alérgenos, preview de coste, historial, export, seguridad y backups.
- Reescritura de `AGENTS.md` para reducir duplicación y fijar invariantes operativos.
- Actualización de `project-memory/` con las nuevas decisiones.
- Corrección de contradicciones detectadas por las tres auditorías:
  - presupuesto duro vs relajable;
  - identidad ticket/consumo/despensa/sobras;
  - alérgenos sin modelo;
  - producto compartido entre ingredientes;
  - escalado entero del optimizador;
  - CP fijo vs configurable;
  - móvil vs `127.0.0.1`;
  - SQLite en OneDrive;
  - terminología “receta”.

### Archivos

- `PLAN.md`
- `TASKS.md`
- `AGENTS.md`
- `project-memory/project-overview.md`
- `project-memory/architecture.md`
- `project-memory/decisions.md`
- `project-memory/changelog.md`
- `project-memory/next-steps.md`

### Motivo

- Convertir los contratos centrales en especificaciones implementables y verificables antes de escribir código.
- Eliminar contradicciones entre documentos.
- Reducir alcance y deuda técnica del MVP.

## 2026-10-25 — Creación inicial

### Cambios

- Creación de `PLAN.md` con alcance, requisitos, stack, arquitectura, modelo de datos, optimizador, integración con Mercadona, riesgos y criterios de aceptación.
- Creación de `TASKS.md` con fases accionables F0-F5 y backlog.
- Creación de `AGENTS.md` con instrucciones operativas para agentes.
- Inicialización de `project-memory/`.
- Verificación preliminar de la API de Mercadona: CP 22002 → almacén 4389; 152 subcategorías; ~4.327 productos.

### Archivos

- `PLAN.md`
- `TASKS.md`
- `AGENTS.md`
- `project-memory/project-overview.md`
- `project-memory/architecture.md`
- `project-memory/decisions.md`
- `project-memory/changelog.md`
- `project-memory/next-steps.md`

### Motivo

- Cerrar el alcance y el stack antes de implementar.
- Dejar una fuente de verdad para agentes y para la memoria del proyecto.
- Ajustar el producto al requisito: menú sin recetas, solo comidas y cenas, presupuesto y días configurables.
