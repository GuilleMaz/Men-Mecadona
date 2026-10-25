# Changelog

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
