# Next Steps

## Estado

F4.1-F4.9 completadas el 2026-10-26. Siguiente: F5 (calidad, resiliencia y entrega).

- Backend: Ruff, formato, mypy strict y 336 tests en verde.
- Frontend: ESLint, Prettier, TypeScript estricto, 49 tests y build en verde.
- Catálogo real: 152/152 subcategorías, 4.540 productos vistos, 4.288 únicos, 178 categorías, 7,74 s, `success`, CP 22002 / almacén 4389.
- Dominio: 110 ingredientes, 212 mapeos únicos, 60 platos sin pasos; `validate_seed.py` en verde.
- Alérgenos: 212 productos mapeados; 210 actualizados en la primera carga real (2 fallos transitorios reintentables), 11-12 `unknown`, 29 `partial`.
- Coste: `plan_purchase` canónico exacto; identidad `ticket + pantry_consumption = consumption + leftover`; preview sin persistencia.
- F4.1-F4.5: migraciones `20261026_0003` y `20261026_0004`, `MenuSettings` versionado, CP-SAT en dos etapas con pista greedy y fallback, diagnósticos de inviabilidad y `MenuService` transaccional con lista canónica.
- F4.6: API `/api/menus` completa (generación, historial, detalle, bloqueo, swap, exclude, regenerate, revalidate, lista, checkbox/«ya lo tengo» y export markdown/CSV). `generate` hereda del perfil los campos omitidos y devuelve `infeasible`/`timeout` sin persistir.
- F4.7-F4.8: UI de generación con modal de inviabilidad, rejilla días × comida/cena, barra de presupuesto, banner `stale`, acciones de menú y lista de la compra con secciones, checkboxes, «ya lo tengo», total sticky, despensa, sobras e identidad contable.
- F4.9: 29 tests nuevos de horizontes/personas, presupuestos, pescado, `unknown`, producto compartido, `base_servings`, bloqueos/regeneración, preview contra lista y workers/semilla. Dry-run 16/16 y benchmark 14d/4p con p95 4,30 s.
- Smoke real por API sobre copia de la base: generación de 1 día/2 personas con ticket 13,50 €, swap 19,30 €, exclude 18,00 €, regenerate 14,65 €, lista de 10 líneas, «ya lo tengo» 10,95 €/9 líneas, identidad correcta y preview imposible con mínimo 10,55 €.
- `run.ps1` aplica `alembic upgrade head` antes de arrancar; el arranque carga el seed y refresca alérgenos en segundo plano.
- F1 publicada en `origin/main` con `e938016`; F2 con `0c9909c`; F3 con `1dd864e`; checkpoint F4.1-F4.5 con `fd563f5`.
- Base SQLite en `%LOCALAPPDATA%\Cesta`, fuera de OneDrive; migraciones 0003 y 0004 aplicadas a la copia local.

## Alta prioridad

- F5.1: fallback a última copia solo si es 22002/4389, banner de precios desactualizados con delta y revalidación al abrir menús guardados.
- F5.2: responsive 1280/768 px, lista imprimible A4, accesibilidad, privacidad e historial inmutable de menús.
- F5.3: exportación markdown/CSV ya implementada; falta auditoría de dependencias, backup/restore SQLite y checklist de seguridad de producción.
- F5.4: README con instalación, uso, arquitectura, capturas/descripción de pantallas y limitaciones.
- F5.5: medir sync, generación y endpoints; benchmark 14d/4p ya disponible en `scripts/benchmark_menu.py`.
- F5.6: `npm run build`, servir el frontend compilado desde FastAPI y `run.ps1 -Prod`.
- F5.7: test de flujo crear menú → ver menú → lista, contrato «sin pasos» y privacidad sin telemetría.
- Al cerrar F5: `.\finish-phase.ps1 -Phase F5 -Summary "calidad, seguridad y entrega"`.

## Prioridad media

- Historial de menús en la UI (`/history`) usando `GET /api/menus`, hoy solo expuesto por API.
- Revisar la semántica de `exclude` con `scope=menu` para bloques repetidos.
- Migrador de `MenuSettings.version` antes de cambiar el esquema del snapshot.

## Baja prioridad / backlog

- Cambio de CP desde la UI.
- Acceso móvil por LAN con autenticación.
- Arrastre de despensa entre menús.
- Historial de precios y gráficos.
- Alertas de bajadas de precio.
- Varios perfiles.
- Exportación PDF.
- PWA/offline.
- Docker y VPS.
- Macros y calorías.
- Playwright E2E.
- Comparador de formatos y alternativas automáticas.

## Bugs

- Ninguno conocido en el código actual.
- Deuda menor backend: `starlette.testclient` emite un aviso de deprecación sugiriendo `httpx2`; revisar al actualizar FastAPI/Starlette.
- Deuda menor frontend: el CLI de shadcn no puede inicializar de forma no interactiva; los componentes nuevos se copian a mano (incluido `dialog.tsx`).
- Alérgenos: 12 productos mapeados sin datos suficientes quedan `unknown`; 29 quedan `partial`. Con alérgenos declarados se excluyen (fail-closed).

## Riesgos

- La API de Mercadona es no oficial y puede cambiar.
- El almacén 4389 debe confirmarse; si no, no se generan menús (ya se valida en el cliente y en `MenuService`).
- La API aplica rate limiting/WAF con 403 transitorios bajo ráfagas; la sync debe mantener concurrencia 4 y reintentos con backoff.
- El id de producto es textual y puede incluir variantes de peso (`"81649.1"`); no asumir enteros.
- El mapeo ingrediente → producto es la parte más frágil; excluir `approx_size`, `selling_method != 0` y formatos no reconocidos.
- El catálogo real cambia entre syncs; los tests no deben fijar conteos de producción.
- Si el proceso se cierra durante una sync, el siguiente arranque la marca como `failed`; el catálogo anterior sigue disponible.
- Los paquetes grandes pueden hacer inviable un presupuesto bajo para 1 persona; la despensa básica ayuda.
- La etapa 2 puede devolver `feasible` sin prueba de optimalidad; es válido, pero `timed_out=true`.
- Los tests de rendimiento no deben exigir tickets idénticos entre ejecuciones limitadas por reloj.
- `regenerate` con `SOLVER_TIMEOUT` devuelve HTTP 200 con sobre de error; el cliente de la UI lo normaliza, pero un consumidor externo debe inspeccionar el cuerpo.
- `GET /api/menus` no filtra por perfil porque el MVP es de perfil único.
- `exclude` con `scope=menu` sustituye todas las apariciones del plato, incluidas las bloqueadas; revisar en F5 si se quiere otra semántica.
- «Ya lo tengo» modifica el snapshot del menú y puede hacer desaparecer líneas; la despensa global no cambia.
- La unidad de `shopping_items` se deriva de `ingredient.base_unit`; si se añade al snapshot, usarla.
- `MenuSettings.version` aún no tiene migrador; una versión futura debe despachar por versión en `MenuService._settings`.
- SQLite debe permanecer fuera de OneDrive; `Settings` ya rechaza esa ruta.
- El intérprete usado por `uv` es el Python 3.13.5 de Anaconda; si se desinstala, `uv sync` deberá resolver otro 3.13.
- Dependencias de frontend muy recientes (React Router 8, Vitest 5, MSW 3, TypeScript 6, ESLint 10): revisar notas de migración al añadir features.
- El bundle principal supera 500 kB; F5 puede valorar code splitting si afecta al arranque.

## Siguiente acción recomendada

1. F5.1: revalidación al abrir un menú guardado y banner de delta de precios.
2. F5.2: responsive, accesibilidad, historial y lista imprimible.
3. F5.3-F5.7: auditoría de dependencias, backup, documentación, rendimiento, build local y flujo de integración.
4. Al cerrar F5: `.\finish-phase.ps1 -Phase F5 -Summary "calidad, seguridad y entrega"`.
