# Next Steps

## Estado

F0 completada el 2026-10-26. F0.1-F0.10 cerradas: backend FastAPI, frontend React, cliente Mercadona 22002/4389, spike de catálogo, spike de OR-Tools, arranque local, seguridad de Host, scripts de calidad y smoke test de `/api/health`.

- Backend: Ruff, formato, mypy strict y 50 tests en verde.
- Frontend: ESLint, Prettier, TypeScript estricto, 10 tests y build en verde.
- OR-Tools 9.15.6755: toy de 28 huecos/60 platos/120 ingredientes resuelto en 3,46-3,47 s; etapa 1 óptima y etapa 2 factible bajo presupuesto.
- `.\run.ps1` arranca backend y frontend; `.\check.ps1` ejecuta toda la calidad.
- `.\finish-phase.ps1 -Phase Fx -Summary "..."` cierra la fase: calidad, commit y push a GitHub.
- Base SQLite en `%LOCALAPPDATA%\Cesta`, fuera de OneDrive.

## Alta prioridad

- F1.1: modelos de catálogo (`Category`, `Product`, `SyncRun`, `SyncCategoryRun`, `ProductAllergen`).
- F1.2: migraciones Alembic con `render_as_batch=True` y SQLite WAL.
- F1.3: normalizador de productos con `Decimal` y cantidades en milésimas.
- F1.4: sync parcial con concurrencia 4, reintentos y upsert idempotente.
- F1.5: endpoints de catálogo y búsqueda.
- F1.6: sync al arrancar sin bloquear la UI.
- F1.7: UI de estado y actualización del catálogo.
- F1.8: tests de catálogo con fixtures sintéticas.

## Notas de la API de Mercadona (2026-10-25)

- `/api/categories/` devuelve un sobre `{count,next,previous,results}`; hoy 26 secciones y 152 subcategorías en una sola página.
- El detalle de una subcategoría trae `products` vacío y los productos dentro de `categories[].products` (los ids hijos no son consultables por separado: devuelven 404).
- El producto usa `display_name` (no `name`); `unit_price` es el precio del paquete y `bulk_price` el precio por unidad base (pack de agua 6 × 1,5 L: 1,62 € frente a 0,18 €/L).
- `pack_size` puede ser decimal (1.5) y representa el tamaño de cada unidad del pack; `unit_size` es la cantidad total y `total_units` el número de unidades.
- El id de producto puede ser texto con sufijo de variante (`"81649.1"`): `external_id` debe ser TEXT.
- Bajo ráfagas, la API responde 403 de forma transitoria; el cliente reintenta 403/429/5xx con 4 intentos y backoff desde 1 s.
- Spike: 4.543 entradas, 4.291 productos únicos; 35 sin tamaño/formato, 383 con `approx_size`, 65 ids de variante. La subcategoría 112 tiene 4 grupos y 38 productos.

## Notas de OR-Tools (2026-10-26)

- El modelo toy usa cotas de `q[p]` ajustadas al mínimo necesario; añadir `+1` empeoraba la etapa 1 y el ticket.
- La etapa 1 de variedad se prueba óptima en menos de 0,4 s.
- La etapa 2 puede agotar sus 3 s y devolver `feasible`; no declarar `optimal` sin prueba. El contrato de F4.4 ya lo contempla.
- Los límites son de tiempo real: con semilla fija y un worker, los tickets pueden variar entre repeticiones. Los tests de optimalidad deben usar instancias pequeñas que terminen antes del límite.

## Prioridad media

- F2: ingredientes, platos, alérgenos, despensa y preferencias.
- F3: coste puro, identidad contable y preview.
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

## Riesgos

- La API de Mercadona es no oficial y puede cambiar.
- El almacén 4389 debe confirmarse; si no, no se generan menús (ya se valida en el cliente).
- La API aplica rate limiting/WAF con 403 transitorios bajo ráfagas; la sync debe mantener concurrencia 4 y reintentos con backoff.
- El id de producto es textual y puede incluir variantes de peso (`"81649.1"`); no asumir enteros.
- El mapeo ingrediente → producto es la parte más frágil; excluir `approx_size` y formatos no reconocidos (35 sin tamaño/formato).
- Los paquetes grandes pueden hacer inviable un presupuesto bajo para 1 persona; la despensa básica ayuda.
- La etapa 2 del optimizador puede devolver `feasible` si no prueba optimalidad en 3 s; es válido, pero debe informarse.
- Los tests de rendimiento no deben exigir tickets idénticos entre ejecuciones limitadas por reloj.
- Los alérgenos requieren datos de producto y política fail-closed.
- SQLite debe permanecer fuera de OneDrive; `Settings` ya rechaza esa ruta.
- El intérprete usado por `uv` es el Python 3.13.5 de Anaconda; si se desinstala, `uv sync` deberá resolver otro 3.13.
- Dependencias de frontend muy recientes (React Router 8, Vitest 5, MSW 3, TypeScript 6, ESLint 10): revisar notas de migración al añadir features.

## Siguiente acción recomendada

1. F1.1 y F1.2: modelos de catálogo y migración inicial con Alembic.
2. F1.3: normalizador de productos con casos dorados (aceite, huevos, pollo, leche y pack 6 × 125 g).
3. F1.4: sync parcial e idempotente con fixtures sintéticas.
4. Al cerrar F1: `.\finish-phase.ps1 -Phase F1 -Summary "catalogo y sincronizacion"`.
