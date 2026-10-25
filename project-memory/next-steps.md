# Next Steps

## Estado

F0 en curso. F0.1 (estructura), F0.2 (backend mínimo), F0.3 (frontend mínimo) y F0.4 (cliente Mercadona) cerradas. Backend: Ruff, mypy strict y 22 tests en verde; frontend: ESLint, Prettier, TypeScript estricto, 6 tests y build en verde. Cliente validado contra la API real: 26 secciones, 152 subcategorías, almacén 4389 y CP 22002.

## Alta prioridad

- F0.5: spike del catálogo completo con concurrencia 4, umbrales e informe en `decisions.md`.
- F0.6: spike de OR-Tools en Windows/Python 3.13; decidir un único solver antes de F4.
- F0.7: `run.ps1` y creación explícita de la base en `%LOCALAPPDATA%\Cesta` (motor y PRAGMA ya existen).
- F0.8: seguridad local básica (bind a 127.0.0.1, validación de `Host`, CORS ya limitado).
- F0.9: scripts de calidad agregados (backend + frontend + scripts).
- F0.10: smoke test de `/api/health` en frontend (MSW ya está configurado).

## Notas de la API de Mercadona (2026-10-25)

- `/api/categories/` devuelve un sobre `{count,next,previous,results}`; hoy 26 secciones y 152 subcategorías en una sola página.
- El detalle de una subcategoría trae `products` vacío y los productos dentro de `categories[].products` (los ids hijos no son consultables por separado: devuelven 404).
- El producto usa `display_name` (no `name`); `unit_price` es el precio del paquete y `bulk_price` el precio por unidad base (5 L → 17,25 € frente a 3,45 €/L).
- La subcategoría 112 (`Aceite, vinagre y sal`) tiene 4 grupos y 38 productos.

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

- Ninguno conocido en el código actual.
- Deuda menor backend: `starlette.testclient` emite un aviso de deprecación sugiriendo `httpx2`; revisar en F0.4/F0.5 (afecta a los tests de `MercadonaClient`, que usan `respx` sobre `httpx`).
- Deuda menor frontend: el CLI de shadcn no puede inicializar de forma no interactiva (ver `decisions.md`); los componentes nuevos deben copiarse a mano o desde el registro hasta que el CLI funcione.

## Riesgos

- La API de Mercadona es no oficial y puede cambiar.
- El almacén 4389 debe confirmarse en F0.4; si no, no se generan menús.
- El mapeo ingrediente → producto es la parte más frágil.
- Los paquetes grandes pueden hacer inviable un presupuesto bajo para 1 persona; la despensa básica ayuda.
- OR-Tools debe validarse en F0.6 antes de F4 (ya instala en Windows/Python 3.13).
- Los alérgenos requieren datos de producto y política fail-closed.
- SQLite debe permanecer fuera de OneDrive.
- El intérprete usado por `uv` es el Python 3.13.5 de Anaconda; si se desinstala, `uv sync` deberá resolver otro 3.13.
- Dependencias de frontend muy recientes (React Router 8, Vitest 5, MSW 3, TypeScript 6, ESLint 10): revisar notas de migración al añadir features.

## Siguiente acción recomendada

1. F0.5: `scripts/spike_catalog.py` con concurrencia 4, métricas del catálogo y umbrales (≥20 secciones, ≥100 subcategorías, ≥3.000 productos).
2. F0.6: spike de OR-Tools con el modelo toy antes de comprometer F4.
