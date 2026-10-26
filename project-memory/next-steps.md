# Next Steps

## Estado

F3 completada el 2026-10-26. F3.1-F3.7 cerradas: unidades, despensa, plan de compra, identidad contable, preview, UI y tests.

- Backend: Ruff, formato, mypy strict y 193 tests en verde.
- Frontend: ESLint, Prettier, TypeScript estricto, 27 tests y build en verde.
- Catálogo real: 152/152 subcategorías, 4.540 productos vistos, 4.288 únicos, 178 categorías, 7,74 s, `success`, CP 22002 / almacén 4389.
- Dominio: 110 ingredientes, 212 mapeos únicos, 60 platos sin pasos; `validate_seed.py` en verde.
- Alérgenos: 212 productos mapeados; 210 actualizados en la primera carga real (2 fallos transitorios reintentables), 11-12 `unknown`, 29 `partial`.
- Coste: `plan_purchase` canónico exacto; identidad `ticket + pantry_consumption = consumption + leftover`; preview sin persistencia; smoke real con 3 platos e identidad correcta.
- `run.ps1` aplica `alembic upgrade head` antes de arrancar; el arranque carga el seed y refresca alérgenos en segundo plano.
- F1 publicada en `origin/main` con el commit `e938016`; F2 con `0c9909c`.
- Base SQLite en `%LOCALAPPDATA%\Cesta`, fuera de OneDrive.

## Alta prioridad

- F4.1: modelos `menus`, `menu_entries`, `menu_entry_ingredients` y `shopping_items` con migración.
- F4.2: filtro de elegibilidad fail-closed reutilizando `EligibilityService`.
- F4.3: modelo CP-SAT con `x`, `q` y `violation[k]`, demanda por coeficientes y presupuesto duro.
- F4.4: objetivo lexicográfico en dos etapas e inviabilidad (`budget` como preview; resto 422).
- F4.5: persistencia de menús, plan de compra materializado y recálculo transaccional.
- F4.6: API completa de menús, swaps, bloqueos, regeneración, revalidación, lista y export.
- F4.7: UI de rejilla días × comida/cena, barra de presupuesto y estados.
- F4.8: UI de lista de la compra con checkboxes, «ya lo tengo», sobras y total sticky.
- F4.9: tests de 1/2/3/7/14 días, 1/2/4/10 personas, presupuestos, bloqueos, variedad, optimalidad por fuerza bruta y dry-run.
- Al cerrar F3/F4: no mezclar cambios de fases.

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
- Los alérgenos requieren datos de producto y política fail-closed; `x99` se combina con ingredientes, pero el etiquetado oficial sigue siendo la fuente legal.
- SQLite debe permanecer fuera de OneDrive; `Settings` ya rechaza esa ruta.
- El intérprete usado por `uv` es el Python 3.13.5 de Anaconda; si se desinstala, `uv sync` deberá resolver otro 3.13.
- Dependencias de frontend muy recientes (React Router 8, Vitest 5, MSW 3, TypeScript 6, ESLint 10): revisar notas de migración al añadir features.
- El seed se carga tras la sync; si el catálogo cambia y un producto mapeado desaparece, `validate_seed.py` lo detecta y el mapeo se queda sin producto.
- F4 debe materializar la lista con `plan_purchase` y verificar `ticket_canónico ≤ ticket_solver ≤ budget`; no debe recalcular con otro criterio.
- El consumo por entrada se reparte con el mayor resto; cualquier cambio de reparto debe conservar la suma exacta.
- La valoración de la despensa usa el formato elegible más barato o el producto por defecto si no hay compra; documentar cualquier cambio en `decisions.md`.

## Siguiente acción recomendada

1. F4.1 y F4.2: migración de menús y filtro de elegibilidad fail-closed.
2. F4.3 y F4.4: modelo CP-SAT, objetivo lexicográfico e inviabilidad.
3. F4.5 y F4.6: persistencia, plan de compra, recálculo y API.
4. F4.7-F4.9: UI, lista, tests y dry-run.
5. Al cerrar F4: `.\finish-phase.ps1 -Phase F4 -Summary "optimizador menu y lista"`.
