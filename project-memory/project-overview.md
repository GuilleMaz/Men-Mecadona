# Project Overview

## Objetivo

**Cesta** es una aplicación web local que genera un menú de **comidas y cenas** para un número de personas, un número de días y un presupuesto total, usando productos y precios de la tienda online de Mercadona.

El usuario indica personas, días y presupuesto. La app devuelve un menú de `días × 2` comidas, el coste real y la lista de la compra. **No incluye recetas ni pasos de cocina**: cada plato es una ficha con nombre, composición de productos y etiquetas.

## Estado Actual

- **Fase:** F0 en curso. F0.1 (estructura), F0.2 (backend mínimo), F0.3 (frontend mínimo) y F0.4 (cliente Mercadona) completadas.
- **Código de aplicación:** backend con FastAPI, `/api/health`, configuración, motor SQLite y cliente Mercadona (CP 22002 / almacén 4389). Frontend con layout en español, navegación Menú/Platos/Ajustes y formulario placeholder.
- **Frontend:** React 19 + Vite 8 + TypeScript 6, Tailwind 4, shadcn/ui por copia, TanStack Query, React Router y React Hook Form + Zod.
- **Integración Mercadona:** validada contra la API real (26 secciones, 152 subcategorías, almacén 4389); tests con fixtures sintéticas y respx, sin red.
- **Documentación:** `PLAN.md`, `TASKS.md`, `AGENTS.md`.
- **Memoria:** inicializada y actualizada.
- **Auditorías:** arquitectura, coherencia y cobertura completadas; verificación final aplicada.
- **Contratos cerrados:** presupuesto, coste, alérgenos, unidades, plan de compra, estados y variedad.
- **Calidad:** backend con Ruff, mypy (strict) y 22 tests; frontend con ESLint, Prettier, TypeScript estricto, 6 tests y build de producción.
- **Última actualización:** 2026-10-25.

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

## Pendientes

- F0.5-F0.10: spike del catálogo, spike de OR-Tools, `run.ps1`, seguridad local, scripts de calidad y smoke test de `/api/health` en la UI.
- F1: catálogo y sync.
- F2: ingredientes, platos, alérgenos y preferencias.
- F3: coste puro y preview.
- F4: optimizador, menú y lista.
- F5: calidad, seguridad y entrega.
- Backlog posterior: CP configurable, LAN/móvil, historial de precios, PDF, PWA, Docker, macros.
