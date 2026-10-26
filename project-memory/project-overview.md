# Project Overview

## Objetivo

**Cesta** es una aplicación web local que genera un menú de **comidas y cenas** para un número de personas, un número de días y un presupuesto total, usando productos y precios de la tienda online de Mercadona.

El usuario indica personas, días y presupuesto. La app devuelve un menú de `días × 2` comidas, el coste real y la lista de la compra. **No incluye recetas ni pasos de cocina**: cada plato es una ficha con nombre, composición de productos y etiquetas.

## Estado Actual

- **Fase:** F0 completada el 2026-10-26 (F0.1-F0.10). Siguiente fase: F1 (catálogo y sincronización).
- **Código de aplicación:** backend con FastAPI, `/api/health`, configuración, motor SQLite, validación de `Host` y cliente Mercadona (CP 22002 / almacén 4389). Frontend con layout en español, navegación Menú/Platos/Ajustes, formulario placeholder e indicador de estado de la API.
- **Frontend:** React 19 + Vite 8 + TypeScript 6, Tailwind 4, shadcn/ui por copia, TanStack Query, React Router y React Hook Form + Zod.
- **Integración Mercadona:** catálogo validado (26 secciones, 152/152 subcategorías, 4.291 productos únicos, 100 % precios parseables, 6,37 s con concurrencia 4); tests con fixtures sintéticas y respx, sin red.
- **OR-Tools:** CP-SAT 9.15.6755 validado en Windows/Python 3.13 con un toy de 28 huecos, 60 platos, 120 ingredientes y paquetes: 3,46-3,47 s por ejecución, etapa 1 óptima y etapa 2 factible bajo presupuesto.
- **Arranque:** `.\run.ps1` arranca backend y frontend, inicializa SQLite fuera de OneDrive y limpia procesos; `.\check.ps1` ejecuta lint, tipos, tests y build.
- **Cierre de fase:** `.\finish-phase.ps1 -Phase Fx -Summary "..."` ejecuta la calidad, crea el commit de la fase y lo sube a GitHub; `-NoPush` y `-SkipChecks` son escapes documentados.
- **Seguridad local:** bind a `127.0.0.1`, CORS solo en desarrollo, allowlist de `Host` y rechazo de bases de datos dentro de OneDrive. Checklist en `SECURITY.md`.
- **Documentación:** `PLAN.md`, `TASKS.md`, `AGENTS.md`, `README.md` y `SECURITY.md`.
- **Memoria:** actualizada con informes de los spikes de catálogo y OR-Tools en `decisions.md`.
- **Contratos cerrados:** presupuesto, coste, alérgenos, unidades, plan de compra, estados y variedad.
- **Calidad:** backend con Ruff, formato, mypy (strict) y 50 tests; frontend con ESLint, Prettier, TypeScript estricto, 10 tests y build de producción.
- **Última actualización:** 2026-10-26.

## Tecnologías

- Backend: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic.
- Base de datos: SQLite WAL en `%LOCALAPPDATA%\Cesta`, fuera de OneDrive.
- Optimización: OR-Tools CP-SAT.
- Cliente HTTP: httpx + tenacity.
- Frontend: React 19, Vite, TypeScript, Tailwind CSS 4, shadcn/ui.
- Estado: TanStack Query.
- Tests: pytest, respx, Vitest, Testing Library, MSW.
- Tooling: uv, Ruff, mypy, npm, ESLint, Prettier.

## Módulos Principales

1. **Catálogo Mercadona:** sincronización de categorías, productos, precios, disponibilidad y fallos parciales.
2. **Ingredientes y platos:** seed de ingredientes canónicos, mapeo a productos y platos sin recetas.
3. **Alérgenos:** lista canónica, detección por producto, política fail-closed.
4. **Coste:** unidades base, necesidad neta, paquetes, ticket, consumo, despensa y sobras.
5. **Optimizador:** selección lexicográfica de platos bajo presupuesto y variedad.
6. **Menús:** persistencia, bloqueos, cambios, regeneración e historial.
7. **Lista de la compra:** consolidación, agrupación, checkboxes y exportación.
8. **Preferencias:** exclusiones, alérgenos y despensa.

## Funcionalidades Terminadas

- Alcance y stack definidos.
- Plan detallado y consolidado.
- Fases accionables.
- Guía para agentes.
- Memoria persistente.
- Auditoría documental completada y correcciones aplicadas.
- F0.1: estructura de repositorio, `.gitignore`, `.env.example`, git inicializado.
- F0.2: backend mínimo (FastAPI + uv), `GET /api/health`, configuración validada, motor SQLite con PRAGMA, CORS solo en desarrollo y tooling de calidad.
- F0.3: frontend mínimo (Vite + React + TypeScript), Tailwind 4, shadcn/ui, navegación Menú/Platos/Ajustes, formulario placeholder con Zod, Vitest + Testing Library + MSW, ESLint + Prettier y build de producción.
- F0.4: cliente Mercadona asíncrono con validación de almacén 4389, paginación, reintentos, DTOs, fixtures sintéticas, tests con respx y script de comprobación real.
- F0.5: spike del catálogo completo con concurrencia 4: 26 secciones, 152/152 subcategorías, 4.291 productos únicos, 100 % precios parseables y 6,37 s; informe en `decisions.md`.
- F0.6: spike de OR-Tools CP-SAT con 28 huecos, 60 platos, 120 ingredientes y paquetes; 3,46-3,47 s, `num_search_workers=1` y sin cambio de solver.
- F0.7: `run.ps1`, `scripts/init_db.py` y base SQLite en `%LOCALAPPDATA%\Cesta` con WAL, claves foráneas y busy timeout.
- F0.8: validación de `Host`, CORS solo en desarrollo y checklist de seguridad local.
- F0.9: `check.ps1` con lint, formato, tipos, tests y build de backend y frontend.
- F0.10: indicador de estado del backend en la UI, consumiendo `/api/health`, con MSW en tests.
- Pipeline de cierre: `finish-phase.ps1` ejecuta la calidad, crea el commit y lo sube a GitHub.

## Pendientes

- F1: catálogo y sync.
- F2: ingredientes, platos, alérgenos y preferencias.
- F3: coste puro y preview.
- F4: optimizador, menú y lista.
- F5: calidad, seguridad y entrega.
- Backlog posterior: CP configurable, LAN/móvil, historial de precios, PDF, PWA, Docker, macros.
