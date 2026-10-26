# Cesta

Aplicación web local que genera un menú de **comidas y cenas** para N personas,
N días y un presupuesto, con productos y precios de la tienda online de Mercadona.
Sin recetas ni pasos de cocina: cada plato es una ficha con composición y etiquetas.

> Estado: F4.1-F4.5 completadas (modelos de menú, elegibilidad, optimizador
> CP-SAT, inviabilidad y servicio transaccional de menús). F4.6-F4.9 añadirán la
> API pública, la UI de menú/lista y la batería completa de pruebas. La
> documentación de alcance está en `PLAN.md` y el detalle de ejecución en
> `TASKS.md`.

## Requisitos

- Windows con PowerShell 5.1 o superior.
- Python 3.13 y [`uv`](https://docs.astral.sh/uv/).
- Node.js 22 o superior y `npm`.

## Arranque

```powershell
.\run.ps1
```

Si PowerShell bloquea el script:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

El script:

1. Resuelve `CESTA_DATA_DIR` (por defecto `%LOCALAPPDATA%\Cesta`).
2. Rechaza rutas dentro de OneDrive.
3. Crea el archivo SQLite con WAL, `foreign_keys=ON` y `busy_timeout=5000`.
4. Aplica las migraciones de Alembic.
5. Arranca el backend en `http://127.0.0.1:8000`.
6. Arranca el frontend en `http://localhost:5173`.

La primera vez, si el catálogo está vacío, el backend lo descarga en segundo
plano (CP 22002, almacén 4389). Después carga el seed de ingredientes/platos y
enriquece los alérgenos de los productos mapeados. También puedes hacerlo manual:

```powershell
cd backend
uv run alembic upgrade head
uv run python ..\scripts\sync_catalog.py
uv run python ..\scripts\load_seed.py
uv run python ..\scripts\sync_allergens.py
uv run python ..\scripts\validate_seed.py
```

El estado y el progreso se ven en `Ajustes` → `Catálogo de Mercadona`; las
preferencias (alérgenos, exclusiones y despensa) en la misma pantalla, y el
catálogo de platos en `Platos`. Al abrir un plato, su detalle muestra el coste de
consumo, el coste por ración y el ticket de compra con los precios actuales.

Para detener ambos servicios, pulsa `Ctrl+C`.

## Calidad

```powershell
.\check.ps1
```

Ejecuta Ruff, mypy y pytest en backend; ESLint, Prettier, TypeScript, Vitest y
build en frontend; y Ruff sobre los scripts de Python de la raíz.

## Coste y preview

`POST /api/pricing/preview` calcula el coste de un conjunto de platos para N
personas sin persistir ningún menú y sin aplicar filtros de alérgenos. Devuelve
coste de consumo, ticket, despensa, sobras, coste por plato y por ración, y la
compra estimada. Si no se envía despensa, usa la del perfil.

Reglas verificadas:

- la necesidad neta resta la despensa antes de calcular paquetes;
- el plan de compra mezcla formatos si sale más barato y minimiza el ticket;
- `ticket + despensa = consumo + sobras` se cumple por ingrediente y por cesta;
- el preview y la futura lista de la compra comparten el mismo plan canónico.

## Optimizador y menús

El backend ya puede generar y persistir un menú bajo presupuesto con el catálogo
sintético de pruebas y con el catálogo real:

- `app/services/optimizer.py` resuelve `días × 2` huecos con CP-SAT en dos
  etapas: primero minimiza las violaciones de variedad y después el ticket.
- El presupuesto es duro. Si el mínimo no cabe, devuelve un preview `infeasible`
  con mínimo, déficit y sugerencias; no se guarda como menú.
- `app/services/menu_service.py` persiste el menú y materializa la lista de la
  compra con `plan_purchase`, verificando `ticket == Σ subtotales` y la identidad
  contable.
- La revalidación conserva el snapshot válido y marca `stale` si el nuevo ticket
  no cabe en el presupuesto; nunca se guarda un menú válido por encima del límite.
- La API pública de menús y la UI de rejilla/lista llegan en F4.6-F4.8.

## Cierre de fase

Cada fase se cierra con un único comando:

```powershell
.\finish-phase.ps1 -Phase F3 -Summary "coste puro y preview"
```

El script ejecuta `check.ps1`, rechaza secretos, bases de datos, `node_modules` y
`.venv`, crea el commit `F3: coste puro y preview` y lo sube a
GitHub. Si la calidad falla, no se hace commit. Si el push falla, el commit queda
local y el script termina con error para poder reintentarlo.

## Estructura

```text
backend/    FastAPI + SQLite + OR-Tools
frontend/   React + Vite + TypeScript
scripts/    spikes y utilidades manuales
```

Los datos de dominio están en `backend/app/data/ingredients.yaml` y
`backend/app/data/dishes.yaml`. Cada ingrediente referencia 1-3 productos por
`external_id`; cada plato declara su composición y los flags derivados. Tras
editar el seed:

```powershell
cd backend
uv run python ..\scripts\validate_seed.py
uv run python ..\scripts\load_seed.py
```

`validate_seed.py` comprueba el catálogo real y `load_seed.py` hace upsert
idempotente.

## Documentación

- `PLAN.md`: alcance, contratos y criterios de aceptación.
- `TASKS.md`: fases y tareas.
- `AGENTS.md`: reglas operativas para agentes.
- `SECURITY.md`: checklist de seguridad local.
- `project-memory/`: estado, decisiones y próximos pasos.

## Aviso

Cesta no está afiliada a Mercadona. Los precios y la disponibilidad son los de la
tienda online para el CP 22002 (almacén 4389) y pueden cambiar. La app no sustituye
el etiquetado oficial de alérgenos.
