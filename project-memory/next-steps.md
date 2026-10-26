# Next Steps

## Estado

F4.1-F4.5 completadas el 2026-10-26. Siguiente: F4.6-F4.9.

- Backend: Ruff, formato, mypy strict y 270 tests en verde.
- Frontend: ESLint, Prettier, TypeScript estricto, 27 tests y build en verde.
- Catálogo real: 152/152 subcategorías, 4.540 productos vistos, 4.288 únicos, 178 categorías, 7,74 s, `success`, CP 22002 / almacén 4389.
- Dominio: 110 ingredientes, 212 mapeos únicos, 60 platos sin pasos; `validate_seed.py` en verde.
- Alérgenos: 212 productos mapeados; 210 actualizados en la primera carga real (2 fallos transitorios reintentables), 11-12 `unknown`, 29 `partial`.
- Coste: `plan_purchase` canónico exacto; identidad `ticket + pantry_consumption = consumption + leftover`; preview sin persistencia.
- F4.1-F4.5: migraciones `20261026_0003` y `20261026_0004`, `MenuSettings` versionado, CP-SAT en dos etapas con pista greedy y fallback, diagnósticos de inviabilidad y `MenuService` transaccional con lista canónica, snapshot de composición y validación de sync 22002/4389.
- Smoke real: 7 días/2 personas con 70/50/42 € (49,85/41,05/40,10 €), 45 € con `relaxed` (40,25 €, una violación de pescado) y 14 días/4 personas en 3,74 s (111,83 €); presupuesto de 1 € con mínimo canónico 45,40 € y déficit 44,40 €. Los tickets exactos pueden variar por el límite de reloj; lo estable es el estado y el presupuesto.
- `run.ps1` aplica `alembic upgrade head` antes de arrancar; el arranque carga el seed y refresca alérgenos en segundo plano.
- F1 publicada en `origin/main` con el commit `e938016`; F2 con `0c9909c`; F3 con `1dd864e`.
- Base SQLite en `%LOCALAPPDATA%\Cesta`, fuera de OneDrive; migraciones 0003 y 0004 aplicadas a la copia local.

## Alta prioridad

- F4.6: API de menús (`generate`, historial, detalle, bloqueo, swap, exclude, regenerate, revalidate, lista, checkbox y export) sobre `MenuService`.
- F4.7: UI de rejilla días × comida/cena, barra de presupuesto y estados.
- F4.8: UI de lista de la compra con checkboxes, «ya lo tengo», sobras y total sticky.
- F4.9: tests de 1/2/3/7/14 días, 1/2/4/10 personas, presupuestos, bloqueos, variedad, optimalidad por fuerza bruta y dry-run.
- Al cerrar F4: no mezclar cambios de fases y ejecutar `.\finish-phase.ps1 -Phase F4 -Summary "..."`.

## Prioridad media

- F5: resiliencia de precios, responsive/accesibilidad, exportación, documentación, rendimiento, build local y tests de integración.

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
- Deuda menor backend: `starlette.testclient` emite un aviso de deprecación sugiriendo `httpx2`; revisar al actualizar FastAPI/Starlette (los tests del cliente usan `respx` sobre `httpx`).
- Deuda menor frontend: el CLI de shadcn no puede inicializar de forma no interactiva (ver `decisions.md`); los componentes nuevos deben copiarse a mano o desde el registro hasta que el CLI funcione.
- Alérgenos: 12 productos mapeados sin datos suficientes quedan `unknown`; 29 quedan `partial` por incoherencia entre alérgenos e ingredientes. Con alérgenos declarados se excluyen (fail-closed), lo que reduce el catálogo elegible.

## Riesgos

- La API de Mercadona es no oficial y puede cambiar.
- El almacén 4389 debe confirmarse; si no, no se generan menús (ya se valida en el cliente).
- La API aplica rate limiting/WAF con 403 transitorios bajo ráfagas; la sync debe mantener concurrencia 4 y reintentos con backoff.
- El id de producto es textual y puede incluir variantes de peso (`"81649.1"`); no asumir enteros.
- El mapeo ingrediente → producto es la parte más frágil; excluir `approx_size`, `selling_method != 0` y formatos no reconocidos (35 sin tamaño/formato en F0.5).
- El catálogo real cambia entre syncs (4.291 en F0.5, 4.288 en F1); los tests no deben fijar conteos de producción.
- La sync puede tardar más si el WAF de Mercadona responde 403; los reintentos y la concurrencia 4 están calibrados con el spike.
- Si el proceso se cierra durante una sync, el siguiente arranque la marca como `failed`; el catálogo anterior sigue disponible.
- Los paquetes grandes pueden hacer inviable un presupuesto bajo para 1 persona; la despensa básica ayuda.
- La etapa 2 del optimizador puede devolver `feasible` si no prueba optimalidad en 3 s; es válido, pero debe informarse.
- Los tests de rendimiento no deben exigir tickets idénticos entre ejecuciones limitadas por reloj.
- La etapa 2 puede devolver `feasible` en 7/14 días por el límite de 3 s; es válido, pero `timed_out=true` y no debe presentarse como óptimo.
- Con alérgenos declarados el catálogo elegible cae mucho (7 platos con gluten en la copia real); para 7 días con `max_repeats=1` la inviabilidad correcta es `repeats` y la sugerencia es permitir repeticiones.
- `exclude_entry` sustituye por un plato elegible determinista, no reoptimiza todo el menú; si no cabe, devuelve `BUDGET_EXCEEDED` y el usuario puede regenerar.
- `revalidate` conserva el snapshot válido (ticket/list) y registra `revalidated_ticket_cents` con `stale` si el nuevo ticket no cabe; la UI de F5 debe mostrar el delta y ofrecer regenerar.
- `exclude` con `scope="menu"` persiste el plato en el snapshot y sustituye todas sus apariciones, incluidas las bloqueadas; revisar el contrato en F4.6 si se quiere otra semántica.
- Si la despensa cubre un ingrediente entero no habrá línea de compra; F4.8 debe mostrar la despensa desde `settings_json`/`pantry_consumption_cents`.
- `MenuSettings.version` aún no tiene migrador; una versión futura debe despachar por versión en `_settings`.
- Los alérgenos requieren datos de producto y política fail-closed; `x99` se combina con ingredientes, pero el etiquetado oficial sigue siendo la fuente legal.
- SQLite debe permanecer fuera de OneDrive; `Settings` ya rechaza esa ruta.
- El intérprete usado por `uv` es el Python 3.13.5 de Anaconda; si se desinstala, `uv sync` deberá resolver otro 3.13.
- Dependencias de frontend muy recientes (React Router 8, Vitest 5, MSW 3, TypeScript 6, ESLint 10): revisar notas de migración al añadir features.
- El seed se carga tras la sync; si el catálogo cambia y un producto mapeado desaparece, `validate_seed.py` lo detecta y el mapeo se queda sin producto.
- F4 debe materializar la lista con `plan_purchase` y verificar `ticket_canónico ≤ ticket_solver ≤ budget`; no debe recalcular con otro criterio.
- El consumo por entrada se reparte con el mayor resto; cualquier cambio de reparto debe conservar la suma exacta.
- La valoración de la despensa usa el formato elegible más barato o el producto por defecto si no hay compra; documentar cualquier cambio en `decisions.md`.

## Siguiente acción recomendada

1. F4.6: implementar la API de menús sobre `MenuService` y mapear `MenuServiceError`/`OptimizerError` al sobre de errores.
2. F4.7 y F4.8: UI de rejilla, barra de presupuesto, estados y lista de la compra.
3. F4.9: completar tests de horizontes/personas, dry-run y benchmark p95.
4. Al cerrar F4: `.\finish-phase.ps1 -Phase F4 -Summary "optimizador menu y lista"`.
