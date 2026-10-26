# Next Steps

## Estado

F2 completada el 2026-10-26. F2.1-F2.10 cerradas: dominio, seed, mapeo, alérgenos, API, UI y tests.

- Backend: Ruff, formato, mypy strict y 161 tests en verde.
- Frontend: ESLint, Prettier, TypeScript estricto, 26 tests y build en verde.
- Catálogo real: 152/152 subcategorías, 4.540 productos vistos, 4.288 únicos, 178 categorías, 7,74 s, `success`, CP 22002 / almacén 4389.
- Dominio: 110 ingredientes, 212 mapeos únicos, 60 platos sin pasos; `validate_seed.py` en verde.
- Alérgenos: 212 productos mapeados; 210 actualizados en la primera carga real (2 fallos transitorios reintentables), 11-12 `unknown`, 29 `partial`.
- `run.ps1` aplica `alembic upgrade head` antes de arrancar; el arranque carga el seed y refresca alérgenos en segundo plano.
- F1 publicada en `origin/main` con el commit `e938016`.
- Base SQLite en `%LOCALAPPDATA%\Cesta`, fuera de OneDrive.

## Alta prioridad

- F3.1: unidades y conversión (`quantity_milli`, `grams_per_unit`).
- F3.2: necesidad neta y despensa parcial/completa/sobre-despensa.
- F3.3: `plan_purchase` canónico, paquetes, consumo y sobras.
- F3.4: identidad contable `ticket + pantry = consumption + leftover`.
- F3.5: `POST /api/pricing/preview` sin persistencia.
- F3.6: UI de coste por plato/ración.
- F3.7: tests de coste (aceite 5 L vs 1 L, huevos, pollo, pack, personas, despensa, preview == lista).
- Al cerrar F2/F3: no mezclar cambios de fases.

## Prioridad media

- F4: optimizador, menú, lista y ajustes.
- F5: resiliencia, seguridad, historial, export y documentación.

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
- Los alérgenos requieren datos de producto y política fail-closed; `x99` se combina con ingredientes, pero el etiquetado oficial sigue siendo la fuente legal.
- SQLite debe permanecer fuera de OneDrive; `Settings` ya rechaza esa ruta.
- El intérprete usado por `uv` es el Python 3.13.5 de Anaconda; si se desinstala, `uv sync` deberá resolver otro 3.13.
- Dependencias de frontend muy recientes (React Router 8, Vitest 5, MSW 3, TypeScript 6, ESLint 10): revisar notas de migración al añadir features.
- El seed se carga tras la sync; si el catálogo cambia y un producto mapeado desaparece, `validate_seed.py` lo detecta y el mapeo se queda sin producto.

## Siguiente acción recomendada

1. F3.1 y F3.2: conversión de unidades y necesidad neta con despensa.
2. F3.3 y F3.4: `plan_purchase`, consumo, sobras e identidad contable.
3. F3.5-F3.7: preview, UI de coste y tests.
4. Al cerrar F3: `.\finish-phase.ps1 -Phase F3 -Summary "coste puro y preview"`.
