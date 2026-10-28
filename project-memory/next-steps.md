# Next Steps

## Estado

F0-F6 completadas el 2026-10-28. **MVP y comidas completas cerrados.**

- Backend: Ruff, formato, mypy strict y 365 tests en verde.
- Frontend: ESLint, Prettier, TypeScript estricto, 56 tests y build en verde.
- Catálogo real: 152/152 subcategorías, 4.542 productos vistos, 4.292 únicos, 178 categorías, 7,72 s, `success`, CP 22002 / almacén 4389.
- Dominio: 110 ingredientes, 212 mapeos únicos, 63 platos sin pasos (55 principales, 8 acompañamientos); `validate_seed.py` en verde.
- Alérgenos: 212 productos mapeados; en la última sync real 211 actualizados y 1 fallo transitorio reintentable; 11-12 `unknown`, 29 `partial`.
- Coste: `plan_purchase` canónico exacto; identidad `ticket + pantry_consumption = consumption + leftover`; preview sin persistencia.
- Resiliencia F5.1: `price_source` (`current|local_copy|unavailable`), generación bloqueada con copia no confirmada, revalidación permitida con copia local válida, delta de precios persistido y visible.
- Entrega F5.2-F5.7: historial `/history`, impresión A4, accesibilidad base, privacidad, auditoría sin hallazgos, backup/restore, producción en un solo proceso, benchmark de endpoints y tests de integración.
- Rendimiento: sync 7,72 s; generación 14d/4p p95 5,22 s con F6; `/api/dishes` p95 32,00 ms; `/api/catalog/status` 9,91 ms; `/api/menus` 5,58 ms.
- F1 publicada en `origin/main` con `e938016`; F2 con `0c9909c`; F3 con `1dd864e`; checkpoint F4.1-F4.5 con `fd563f5`; F4 con `8bf41fe`; F5 cerrada con `32b32ac`; F6 cerrada con `8c1de22`.
- Base SQLite en `%LOCALAPPDATA%\Cesta`, fuera de OneDrive; migración `20261026_0005` aplicada a la copia local.

## Alta prioridad (post-MVP)

- **F6 completada:** plato principal completo, acompañamientos opcionales, topes blandos de proteínas y pescado 2/semana.
- Revisar el warning del bundle principal (>500 kB) y valorar code splitting por rutas.
- Añadir una comprobación de accesibilidad automatizada (axe o equivalente) si se incorpora una dependencia de test.
- Decidir si la revalidación automática al abrir debe respetar un intervalo mínimo (p. ej. 5 min) para no repetir trabajo en navegaciones rápidas.
- Revisar `exclude` con `scope=menu` para bloques repetidos y la semántica de bloqueos.
- Migrador de `MenuSettings.version` antes de cambiar el esquema del snapshot.

## Prioridad media

- Historial de precios y gráficos.
- Cambio de CP/almacén desde la UI y re-sync.
- Acceso desde móvil por LAN con autenticación.
- Arrastre de despensa y sobras entre menús.
- Comparador de formatos y alternativas automáticas.
- Exportación PDF.

## Baja prioridad / backlog

- Alertas de bajadas de precio.
- Varios perfiles.
- PWA/offline.
- Docker y despliegue en VPS.
- Importar/exportar platos.
- Macros y calorías.
- Playwright E2E.

## Bugs

- Ninguno conocido en el código actual.
- Deuda menor backend: `starlette.testclient` emite un aviso de deprecación sugiriendo `httpx2`; revisar al actualizar FastAPI/Starlette.
- Deuda menor frontend: el CLI de shadcn no puede inicializar de forma no interactiva; los componentes nuevos se copian a mano.
- Alérgenos: 12 productos mapeados sin datos suficientes quedan `unknown`; 29 quedan `partial`. Con alérgenos declarados se excluyen (fail-closed).
- La última sync real dejó 1 producto mapeado sin enriquecer por un fallo transitorio; el siguiente arranque/sync lo reintenta.

## Riesgos

- La API de Mercadona es no oficial y puede cambiar.
- El almacén 4389 debe confirmarse; si no, no se generan menús nuevos (ya se valida en cliente, `price_source` y `MenuService`).
- La API aplica rate limiting/WAF con 403 transitorios bajo ráfagas; la sync debe mantener concurrencia 4 y reintentos con backoff.
- El id de producto es textual y puede incluir variantes de peso (`"81649.1"`); no asumir enteros.
- El mapeo ingrediente → producto es la parte más frágil; excluir `approx_size`, `selling_method != 0` y formatos no reconocidos.
- El catálogo real cambia entre syncs; los tests no deben fijar conteos de producción.
- Si el proceso se cierra durante una sync, el siguiente arranque la marca como `failed`; la copia válida anterior sigue disponible para consultar/revalidar.
- Los paquetes grandes pueden hacer inviable un presupuesto bajo para 1 persona; la despensa básica ayuda.
- La etapa 2 puede devolver `feasible` sin prueba de optimalidad; es válido, pero `timed_out=true`.
- Los tests de rendimiento no deben exigir tickets idénticos entre ejecuciones limitadas por reloj.
- `regenerate` con `SOLVER_TIMEOUT` devuelve HTTP 200 con sobre de error; el cliente de la UI lo normaliza, pero un consumidor externo debe inspeccionar el cuerpo.
- `GET /api/menus` no filtra por perfil porque el MVP es de perfil único.
- `exclude` con `scope=menu` sustituye todas las apariciones del plato, incluidas las bloqueadas.
- «Ya lo tengo» modifica el snapshot del menú y puede hacer desaparecer líneas; la despensa global no cambia.
- La unidad de `shopping_items` se deriva de `ingredient.base_unit`; si se añade al snapshot, usarla.
- `MenuSettings.version` aún no tiene migrador; una versión futura debe despachar por versión en `MenuService._settings`.
- SQLite debe permanecer fuera de OneDrive; `Settings` ya rechaza esa ruta.
- El intérprete usado por `uv` es el Python 3.13.5 de Anaconda; si se desinstala, `uv sync` deberá resolver otro 3.13.
- Dependencias de frontend muy recientes (React Router 8, Vitest 5, MSW 3, TypeScript 6, ESLint 10): revisar notas de migración al añadir features.
- El bundle principal supera 500 kB (541,60 kB, 162,13 kB gzip); no afecta al DoD, pero conviene code splitting.
- `price_source` bloquea generar durante una sync en curso; la UI muestra la copia local y el motivo.
- F6 exige principales completos y limita fuentes baratas: el ticket medio sube; el benchmark 14d/4p dio p95 5,22 s y tickets variables según el límite de reloj.
- Los topes de proteína son blandos: con presupuesto ajustado el menú puede ser `relaxed`; se informa en la UI.
- La clasificación `main|complement` es heurística por raciones y puede revisarse (por ejemplo, el umbral 0,5).
- Los menús históricos anteriores a F6 conservan `course='main'` y pueden mostrar un complemento como plato único hasta regenerarse.
- El cambio de unicidad de `menu_entries` exige migración batch en SQLite; la conexión de Alembic desactiva `foreign_keys` durante la migración, pero hay que probar cualquier migración futura con datos históricos.
- `regenerate` descarta acompañamientos que no caben y la UI lo avisa comparando conteos; no se persiste el motivo por acompañamiento.

## Siguiente acción recomendada

1. Cerrar F6 con `.\finish-phase.ps1 -Phase F6 -Summary "comidas completas y acompañamientos"`.
2. Abordar code splitting y una auditoría de accesibilidad automatizada como trabajo post-MVP.
3. Revisar la semántica de `exclude` con `scope=menu` y añadir el migrador de `MenuSettings.version` antes de cambiar el snapshot.
4. Mantener la sync real y el benchmark como comprobaciones manuales antes de release.
