# Next Steps

## Estado

F0 en curso. F0.1 (estructura), F0.2 (backend mínimo), F0.3 (frontend mínimo), F0.4 (cliente Mercadona) y F0.5 (spike del catálogo) cerradas. Backend: Ruff, mypy strict y 26 tests en verde; frontend: ESLint, Prettier, TypeScript estricto, 6 tests y build en verde. Catálogo validado: 26 secciones, 152/152 subcategorías, 4.291 productos únicos, 100 % precios parseables, 6,37 s con concurrencia 4 y 0 fallos.

## Alta prioridad

- F0.6: spike de OR-Tools en Windows/Python 3.13; decidir un único solver antes de F4.
- F0.7: `run.ps1` y creación explícita de la base en `%LOCALAPPDATA%\Cesta` (motor y PRAGMA ya existen).
- F0.8: seguridad local básica (bind a 127.0.0.1, validación de `Host`, CORS ya limitado).
- F0.9: scripts de calidad agregados (backend + frontend + scripts).
- F0.10: smoke test de `/api/health` en frontend (MSW ya está configurado).

## Notas de la API de Mercadona (2026-10-25)

- `/api/categories/` devuelve un sobre `{count,next,previous,results}`; hoy 26 secciones y 152 subcategorías en una sola página.
- El detalle de una subcategoría trae `products` vacío y los productos dentro de `categories[].products` (los ids hijos no son consultables por separado: devuelven 404).
- El producto usa `display_name` (no `name`); `unit_price` es el precio del paquete y `bulk_price` el precio por unidad base (pack de agua 6 × 1,5 L: 1,62 € frente a 0,18 €/L).
- `pack_size` puede ser decimal (1.5) y representa el tamaño de cada unidad del pack; `unit_size` es la cantidad total y `total_units` el número de unidades.
- El id de producto puede ser texto con sufijo de variante (`"81649.1"`): `external_id` debe ser TEXT.
- Bajo ráfagas, la API responde 403 de forma transitoria; el cliente reintenta 403/429/5xx con 4 intentos y backoff desde 1 s.
- Spike: 4.543 entradas, 4.291 productos únicos; 35 sin tamaño/formato, 383 con `approx_size`, 65 ids de variante. La subcategoría 112 tiene 4 grupos y 38 productos.

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
- Deuda menor backend: `starlette.testclient` emite un aviso de deprecación sugiriendo `httpx2`; revisar al actualizar FastAPI/Starlette (los tests del cliente usan `respx` sobre `httpx`).
- Deuda menor frontend: el CLI de shadcn no puede inicializar de forma no interactiva (ver `decisions.md`); los componentes nuevos deben copiarse a mano o desde el registro hasta que el CLI funcione.

## Riesgos

- La API de Mercadona es no oficial y puede cambiar.
- El almacén 4389 debe confirmarse; si no, no se generan menús (ya se valida en el cliente).
- La API aplica rate limiting/WAF con 403 transitorios bajo ráfagas; la sync debe mantener concurrencia 4 y reintentos con backoff.
- El id de producto es textual y puede incluir variantes de peso (`"81649.1"`); no asumir enteros.
- El mapeo ingrediente → producto es la parte más frágil; excluir `approx_size` y formatos no reconocidos (35 sin tamaño/formato).
- Los paquetes grandes pueden hacer inviable un presupuesto bajo para 1 persona; la despensa básica ayuda.
- OR-Tools debe validarse en F0.6 antes de F4 (ya instala en Windows/Python 3.13).
- Los alérgenos requieren datos de producto y política fail-closed.
- SQLite debe permanecer fuera de OneDrive.
- El intérprete usado por `uv` es el Python 3.13.5 de Anaconda; si se desinstala, `uv sync` deberá resolver otro 3.13.
- Dependencias de frontend muy recientes (React Router 8, Vitest 5, MSW 3, TypeScript 6, ESLint 10): revisar notas de migración al añadir features.

## Siguiente acción recomendada

1. F0.6: spike de OR-Tools con el modelo toy (28 huecos, 60 platos, 120 ingredientes) antes de comprometer F4.
2. F0.7-F0.10: arranque local, seguridad, scripts de calidad y smoke test.
