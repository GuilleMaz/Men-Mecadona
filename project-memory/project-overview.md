# Project Overview

## Objetivo

**Cesta** es una aplicación web local que genera un menú de **comidas y cenas** para un número de personas, un número de días y un presupuesto total, usando productos y precios de la tienda online de Mercadona.

El usuario indica personas, días y presupuesto. La app devuelve un menú de `días × 2` comidas, el coste real y la lista de la compra. **No incluye recetas ni pasos de cocina**: cada plato es una ficha con nombre, composición de productos y etiquetas.

## Estado Actual

- **Fase:** F0-F6 completadas el 2026-10-28. MVP y comidas completas cerrados.
- **Código de aplicación:** backend con FastAPI, `/api/health`, configuración, motor SQLite, validación de `Host`, cliente Mercadona (CP 22002 / almacén 4389), catálogo persistente con sync parcial, ingredientes/platos con seed idempotente, alérgenos fail-closed, perfil, exclusiones, despensa, motor de costes puro con preview, optimizador CP-SAT en dos etapas, servicio transaccional de menús y API `/api/menus` completa. F5 añade resiliencia de precios, historial, impresión A4, producción local en un solo proceso, backup/restore y auditoría. Frontend con layout en español, navegación Menú/Historial/Platos/Ajustes, formulario de perfil persistente, generación de menú con modal de inviabilidad, rejilla días × comida/cena, barra de presupuesto, acciones de menú, revalidación al abrir, lista de la compra con checkboxes, «ya lo tengo», totales e identidad contable.
- **Frontend:** React 19 + Vite 8 + TypeScript 6, Tailwind 4, shadcn/ui por copia, TanStack Query, React Router y React Hook Form + Zod.
- **Integración Mercadona:** sync real validada: 26 secciones, 152/152 subcategorías, 4.542 productos vistos, 4.292 productos únicos persistidos, 178 categorías y 7,72 s con concurrencia 4. Tests con fixtures sintéticas y respx, sin red.
- **Catálogo:** migraciones Alembic (`render_as_batch`), upsert por `external_id`, normalización a céntimos y milésimas, fallo parcial sin ocultar productos de categorías fallidas, lock de proceso y refresh de arranque a las 24 h.
- **Resiliencia (F5):** `price_source` distingue `current`, `local_copy` y `unavailable`; una sync fallida permite consultar/revalidar menús pero no generar, y una copia de otro almacén bloquea cualquier recálculo. El menú guarda ticket anterior, revalidado y delta; la UI revalida al abrir y muestra el aviso.
- **Dominio F2:** 110 ingredientes, 212 mapeos explícitos a productos, 60 platos sin pasos y 212 productos mapeados con alérgenos reales (210 actualizados en la primera carga real, 2 fallos transitorios; 11-12 `unknown`, 29 `partial`). `seed_version` por hash y soft delete.
- **OR-Tools:** CP-SAT 9.15.6755 validado en Windows/Python 3.13 con un toy de 28 huecos, 60 platos, 120 ingredientes y paquetes: 3,46-3,47 s por ejecución, etapa 1 óptima y etapa 2 factible bajo presupuesto.
- **Arranque:** `.\run.ps1` arranca backend y frontend, inicializa SQLite fuera de OneDrive, aplica migraciones, carga el seed y enriquece alérgenos en segundo plano; `.\check.ps1` ejecuta lint, tipos, tests y build.
- **Cierre de fase:** `.\finish-phase.ps1 -Phase Fx -Summary "..."` ejecuta la calidad, crea el commit de la fase y lo sube a GitHub; `-NoPush` y `-SkipChecks` son escapes documentados. F1 se publicó en `origin/main` con el commit `e938016`.
- **Seguridad local:** bind a `127.0.0.1`, CORS solo en desarrollo, allowlist de `Host` y rechazo de bases de datos dentro de OneDrive. Checklist en `SECURITY.md`.
- **Documentación:** `PLAN.md`, `TASKS.md`, `AGENTS.md`, `README.md` y `SECURITY.md`.
- **Memoria:** actualizada con informes de los spikes y las decisiones de F0-F4 en `decisions.md`.
- **Contratos cerrados:** presupuesto, coste, alérgenos, unidades, plan de compra, estados y variedad. F6 deja planificado el contrato de plato principal completo y acompañamientos opcionales.
- **Coste (F3):** `plan_purchase` canónico exacto, necesidad neta con despensa, ticket, consumo, sobras e identidad `ticket + pantry_consumption = consumption + leftover`; preview sin persistencia y sin filtros de alérgenos.
- **Optimizador (F4.1-F4.4):** migraciones `20261026_0003` y `20261026_0004` con menús, snapshots y relajaciones; elegibilidad fail-closed reutilizada; CP-SAT con `x`, `q` y violaciones de variedad; pista greedy determinista y fallback sin presupuesto para presupuestos ajustados; dos etapas lexicográficas; estados `optimal`/`feasible`/`relaxed`/`infeasible`/`timeout`; preview de presupuesto con mínimo canónico, déficit y sugerencias; diagnóstico de bloqueos, repeticiones, mínimos y asignación.
- **Menús (F4.5):** `MenuService` transaccional que materializa la lista con `plan_purchase`, reparte céntimos por entrada, preserva `checked` por producto, valida la sync 22002/4389 y recalcula tras swap, exclude, regenerate, revalidate y «ya lo tengo». La revalidación conserva el snapshot válido y expone el ticket recalculado en `revalidated_ticket_cents` si supera el presupuesto; los recálculos usan la composición persistida.
- **API de menús (F4.6):** router `/api/menus` con generación, historial paginado, detalle, bloqueo, swap, exclude, regenerate, revalidate, lista agrupada por sección, checkbox/«ya lo tengo» y export markdown/CSV. `generate` hereda del perfil los campos omitidos, devuelve `infeasible`/`timeout` sin persistir y mapea los errores de dominio con `reason`.
- **UI de menú y compra (F4.7-F4.8):** `/menus/:id` con rejilla, barra de presupuesto, banner `stale`, modal de inviabilidad y acciones; `/menus/:id/shopping-list` con secciones, «ya lo tengo» sobre el snapshot del menú, total sticky, sobras, coste por comida/día/persona e identidad contable.
- **Entrega (F5):** `/history` paginado, enlace «Saltar al contenido», foco visible y hoja de impresión A4; `run.ps1 -Prod` compila y sirve `frontend/dist` desde FastAPI; `audit.ps1`, `backup_db.py`, `restore_db.py` y `benchmark_endpoints.py`.
- **Pruebas F4.9:** 29 tests nuevos de horizontes/personas, presupuestos, pescado, `unknown`, producto compartido, `base_servings`, bloqueos/regeneración, preview contra lista y workers/semilla. `dry_run_menu.py` validó 16/16 escenarios.
- **Pruebas F5:** flujo generar → detalle → lista, historial inmutable, contrato sin pasos, privacidad sin telemetría, build servido, backup/restore, sync fallida y almacén mezclado.
- **Calidad:** backend con Ruff, formato, mypy (strict) y 365 tests; frontend con ESLint, Prettier, TypeScript estricto, 56 tests y build de producción. `pip-audit` y `npm audit` sin hallazgos. Smoke real por API sobre copia del catálogo: generación 13,50 €, swap 19,30 €, exclude 18,00 €, regenerate 14,65 €, «ya lo tengo» 10,95 € y preview imposible con mínimo 10,55 €.
- **Rendimiento:** sync 7,72 s; generación 14d/4p p95 5,22 s con F6; `/api/dishes` p95 32,00 ms; `/api/catalog/status` 9,91 ms; `/api/menus` 5,58 ms.
- **F6 (2026-10-28):** `dishes.role` (`main|complement`) y `primary_protein` derivados de la composición; `menu_entries.course` con unicidad por curso; optimizador solo de principales con topes blandos por fuente, misma proteína por día y pescado 2/semana; endpoints de acompañamiento; UI de principal + acompañamiento; 3 acompañamientos nuevos. 55 principales y 8 acompañamientos.
- **Última actualización:** 2026-10-28. F6 verificada con 365 tests backend, 56 frontend, dry-run 16/16 y benchmark 14d/4p p95 5,22 s.

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
- F1.1: modelos `categories`, `products`, `sync_runs`, `sync_category_runs` y `product_allergens` con constraints e índices.
- F1.2: Alembic con `render_as_batch`, WAL, `foreign_keys` y `busy_timeout`; migración inicial verificada y sin deriva.
- F1.3: normalizador con `Decimal`, céntimos enteros, milésimas de g/ml/unidad, packs, peso variable y mostrador.
- F1.4: sync real con concurrencia 4, reintentos, upsert idempotente, fallo parcial y lock.
- F1.5: API de estado, sync, árbol de categorías, búsqueda, filtro y detalle de producto.
- F1.6: refresh de arranque en segundo plano si el catálogo está vacío o tiene más de 24 h.
- F1.7: tarjeta de estado del catálogo en Ajustes con botón de sync y polling de progreso.
- F1.8: 70 tests backend nuevos y 6 de frontend, sin red.
- F2.1: modelos `ingredients`, `ingredient_products`, `dishes`, `dish_ingredients`, `profiles`, `exclusions` y `pantry_items` con constraints e índices parciales.
- F2.2: 110 ingredientes con unidad base, grupo, ración, alérgenos y 1-3 productos.
- F2.3: 212 mapeos explícitos únicos validados contra el catálogo real.
- F2.4: cliente de detalle, parser de alérgenos y enriquecimiento fail-closed de 212 productos reales.
- F2.5: 60 platos sin pasos, flags derivados y cobertura de comida/cena/proteína/pescado/legumbre/carne roja/cenas ligeras.
- F2.6: cargador de seed idempotente con `seed_version`, soft delete y `--dry-run`.
- F2.7: `scripts/validate_seed.py` y validación contra el catálogo.
- F2.8: API de platos, ingredientes, alérgenos, perfil, exclusiones y despensa.
- F2.9: UI de perfil, catálogo de platos, alérgenos, exclusiones y despensa.
- F2.10: 41 tests backend y 10 frontend nuevos, sin red.
- F3.1: unidades, escalado por personas/raciones y validación de unidad base producto/ingrediente; `grams_per_unit` obligatorio por pieza.
- F3.2: necesidad neta con despensa parcial, completa y sobre-despensa.
- F3.3: `plan_purchase` canónico exacto, mezcla de formatos, consumo por coste unitario ascendente y sobras.
- F3.4: identidad contable por ingrediente y por cesta, con redondeo half-up solo al final.
- F3.5: `POST /api/pricing/preview` sin persistencia, con despensa del perfil u override y sin filtros de alérgenos.
- F3.6: `DishCostCard` con coste de consumo, coste por ración, ticket, despensa, sobras y líneas de compra.
- F3.7: 32 tests backend y 1 frontend nuevos; casos de aceite 5 L vs 1 L, huevos, pollo, pack 6 × 125 g, 1 vs 4 personas y despensa.
- F4.6: API completa de menús con preview de inviabilidad/timeout sin persistir, lista agrupada, «ya lo tengo» y export seguro.
- F4.7: UI de generación, rejilla de menú, barra de presupuesto, estados, modal de inviabilidad y acciones.
- F4.8: lista de la compra con secciones, checkboxes, «ya lo tengo», total sticky, despensa, costes e identidad contable.
- F4.9: 29 tests nuevos, dry-run de 16 escenarios y benchmark 14d/4p.
- F5: `price_source`, migración `20261026_0005`, delta de precios, revalidación al abrir, historial, impresión A4, producción local en un solo proceso, backup/restore, auditoría, benchmark de endpoints y tests de entrega/privacidad.
- F6: `dishes.role`/`primary_protein`, `menu_entries.course`, endpoints de acompañamiento, optimizador de principales con topes blandos, UI de ambos cursos, 3 acompañamientos nuevos y migración `20261026_0006`.
- Pipeline de cierre: `finish-phase.ps1` ejecuta la calidad, crea el commit y lo sube a GitHub.

## Pendientes

- Post-MVP: code splitting del bundle, CP/almacén configurable, LAN/móvil con autenticación, historial de precios, PDF, PWA, Docker, macros y comparador de formatos.
