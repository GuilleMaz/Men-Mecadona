# Next Steps

## Estado

F0 en curso. F0.1 (estructura) y F0.2 (backend mínimo) cerradas: `uv sync`, Ruff, mypy strict y 14 tests en verde; `/api/health` responde `{"status":"ok"}`. El frontend aún no existe.

## Alta prioridad

- F0.3: frontend mínimo con Vite, React, TypeScript, Tailwind y tests.
- F0.4: cliente Mercadona mínimo para CP 22002 / almacén 4389.
- F0.5: spike del catálogo con umbrales y informe.
- F0.6: spike de OR-Tools en Windows/Python 3.13; decidir un único solver antes de F4.
- F0.7: `run.ps1` y base de datos en `%LOCALAPPDATA%\Cesta` (el motor y los PRAGMA ya existen en `app/db.py`, falta el arranque y la creación explícita).
- F0.8: seguridad local básica (bind, CORS, Host). CORS de desarrollo ya está limitado a `http://localhost:5173`.
- F0.9: scripts de lint, tipos y tests.
- F0.10: smoke test de `/api/health` en frontend.

## Prioridad media

- F1: catálogo, normalización, sync parcial y búsqueda.
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

- Ninguno conocido en el código actual. Deuda menor: `starlette.testclient` emite un aviso de deprecación sugiriendo `httpx2`; revisar en F0.4/F0.5 (afecta a los tests de `MercadonaClient`, que usan `respx` sobre `httpx`).

## Riesgos

- La API de Mercadona es no oficial y puede cambiar.
- El almacén 4389 debe confirmarse en F0.4; si no, no se generan menús.
- El mapeo ingrediente → producto es la parte más frágil.
- Los paquetes grandes pueden hacer inviable un presupuesto bajo para 1 persona; la despensa básica ayuda.
- OR-Tools debe validarse en F0.6 antes de F4 (ya instala en Windows/Python 3.13).
- Los alérgenos requieren datos de producto y política fail-closed.
- SQLite debe permanecer fuera de OneDrive.
- El intérprete usado por `uv` es el Python 3.13.5 de Anaconda; si se desinstala, `uv sync` deberá resolver otro 3.13.

## Siguiente acción recomendada

1. F0.3: inicializar el frontend con Vite y consumir `/api/health`.
2. F0.4-F0.6: spikes de Mercadona y OR-Tools antes de comprometer F3/F4.
