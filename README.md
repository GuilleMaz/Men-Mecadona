# Cesta

Aplicación web local que genera un menú de **comidas y cenas** para N personas,
N días y un presupuesto, con productos y precios de la tienda online de Mercadona.
Sin recetas ni pasos de cocina: cada plato es una ficha con composición y etiquetas.

> Estado: **F5 completada** (calidad, resiliencia de precios, accesibilidad,
> historial, exportación/impresión, seguridad, rendimiento y build local).
> La documentación de alcance está en `PLAN.md` y el detalle de ejecución en
> `TASKS.md`.

## Requisitos

- Windows con PowerShell 5.1 o superior.
- Python 3.13 y [`uv`](https://docs.astral.sh/uv/).
- Node.js 22 o superior y `npm`.

## Arranque

Desarrollo (backend con recarga + Vite):

```powershell
.\run.ps1
```

Producción local (un solo proceso): compila el frontend y FastAPI sirve la UI y
la API en `http://127.0.0.1:8000`, sin CORS y sin documentación interactiva:

```powershell
.\run.ps1 -Prod
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
6. En desarrollo, arranca Vite en `http://localhost:5173`; con `-Prod`, compila
   el frontend y sirve `frontend/dist` desde FastAPI.

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

En `Menú` se indica personas, días y presupuesto. Al generar se abre
`/menus/:id` con la rejilla de comidas y cenas, el estado del menú, la barra de
presupuesto y las acciones de bloquear, cambiar, «no me gusta», revalidar y
regenerar. Si el mínimo no cabe, se muestra un modal con mínimo, déficit y
sugerencias, y no se guarda ningún menú. La lista de la compra está en
`/menus/:id/shopping-list`, agrupada por secciones, con checkboxes, «ya lo
tengo», total sticky, sobras, coste por comida/día/persona y la identidad
contable visible. `Historial` lista los menús guardados; cada menú conserva el
nombre y el coste congelados de sus platos.

Para detener el servicio, pulsa `Ctrl+C`.

## Pantallas principales

- **Menú:** formulario de personas/días/presupuesto, equivalencias €/día y
  €/comida, generación con estados de carga, menú inviable, timeout y error.
- **Menú guardado:** rejilla días × comida/cena, estado (`optimal`, `feasible`,
  `relaxed`), aviso `stale` con delta de precios, CP/almacén/fecha, bloqueo,
  cambio, exclusión, regeneración y exportación markdown/CSV.
- **Lista de la compra:** secciones, checkboxes, «ya lo tengo» sobre el snapshot
  del menú, total sticky, despensa, sobras, coste por comida/día/persona e
  identidad contable. Se puede imprimir en A4 desde el navegador.
- **Historial:** menús guardados paginados, con ticket, presupuesto, estado y
  enlaces al menú y a la lista.
- **Platos:** búsqueda, filtros, composición, coste del plato y «no me gusta».
- **Ajustes:** catálogo, alérgenos, exclusiones, despensa y aviso de copia local.

## Resiliencia de precios

La app siempre lee de su copia SQLite local. Esa copia solo se usa para precios
actuales si la última sincronización completa corresponde al **CP 22002** y al
**almacén 4389**. Si la última sync falla, la copia válida anterior permite
consultar y revalidar menús guardados, pero **no generar menús nuevos**. Una
copia de otro almacén no se mezcla nunca.

Al abrir un menú guardado se revalida una vez con los precios actuales. Si el
ticket cambia, la UI muestra el ticket anterior, el revalidado y el delta. Si el
ticket supera el presupuesto, se conserva el snapshot válido y se marca `stale`
para que el usuario revalide o regenere.

## Calidad

```powershell
.\check.ps1
```

Ejecuta Ruff, mypy y pytest en backend; ESLint, Prettier, TypeScript, Vitest y
build en frontend; y Ruff sobre los scripts de Python de la raíz. Estado actual:
354 tests backend, 54 tests frontend y build de producción en verde.

Auditoría de dependencias (requiere red):

```powershell
.\audit.ps1
```

`pip-audit` no encontró vulnerabilidades y `npm audit --audit-level=high`
devolvió 0 hallazgos.

## Coste y preview

`POST /api/pricing/preview` calcula el coste de un conjunto de platos para N
personas sin persistir ningún menú y sin aplicar filtros de alérgenos. Devuelve
coste de consumo, ticket, despensa, sobras, coste por plato y por ración, y la
compra estimada. Si no se envía despensa, usa la del perfil.

Reglas verificadas:

- la necesidad neta resta la despensa antes de calcular paquetes;
- el plan de compra mezcla formatos si sale más barato y minimiza el ticket;
- `ticket + despensa = consumo + sobras` se cumple por ingrediente y por cesta;
- el preview y la lista de la compra comparten el mismo plan canónico.

## Optimizador, menús y API

El backend genera y persiste menús bajo presupuesto con el catálogo real:

- `app/services/optimizer.py` resuelve `días × 2` huecos con CP-SAT en dos
  etapas: primero minimiza las violaciones de variedad y después el ticket.
- El presupuesto es duro. Si el mínimo no cabe, devuelve un preview `infeasible`
  con mínimo, déficit y sugerencias; no se guarda como menú.
- `app/services/menu_service.py` persiste el menú y materializa la lista de la
  compra con `plan_purchase`, verificando `ticket == Σ subtotales` y la identidad
  contable.
- La revalidación conserva el snapshot válido y marca `stale` si el nuevo ticket
  no cabe en el presupuesto; nunca se guarda un menú válido por encima del límite.
- La API `/api/menus` permite generar, consultar el historial y el detalle,
  bloquear/desbloquear, cambiar, excluir, regenerar, revalidar, consultar la
  lista, marcar comprados, aplicar «ya lo tengo» y exportar en markdown o CSV.
- `POST /api/menus/generate` con `null`/campos omitidos hereda los alérgenos,
  exclusiones y despensa del perfil; una lista explícita los reemplaza.
- Un swap, una exclusión o «ya lo tengo» que superen el presupuesto devuelven
  `BUDGET_EXCEEDED` y no se aplican. `regenerate` conserva los bloqueos.

## Backup y restauración

Cierra la app antes de restaurar. La copia se valida con `PRAGMA integrity_check`
y se escribe de forma atómica.

```powershell
cd backend
uv run python ..\scripts\backup_db.py
uv run python ..\scripts\backup_db.py --output D:\copias\cesta.db
uv run python ..\scripts\restore_db.py --backup D:\copias\cesta.db --force
```

La copia por defecto se guarda en `<CESTA_DATA_DIR>\backups\cesta-<fecha>.db`
(fuera de OneDrive).

## Rendimiento

```powershell
cd backend
uv run python ..\scripts\benchmark_menu.py --runs 20 --days 14 --people 4
uv run python ..\scripts\benchmark_endpoints.py --runs 20
```

- Generación 14 días/4 personas: p95 3,73 s (límite 10 s).
- `/api/dishes`: p95 32,00 ms (límite 200 ms).
- Sync completa: 7,72 s (límite 2 min; 152/152 subcategorías, 4.292 productos).
- `/api/catalog/status`: p95 9,91 ms; `/api/menus`: p95 5,58 ms.

## Cierre de fase

Cada fase se cierra con un único comando:

```powershell
.\finish-phase.ps1 -Phase F5 -Summary "calidad, seguridad y entrega"
```

El script ejecuta `check.ps1`, rechaza secretos, bases de datos, `node_modules` y
`.venv`, crea el commit `F5: calidad, seguridad y entrega` y lo sube a GitHub. Si
la calidad falla, no se hace commit.

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

## Limitaciones del MVP

- Un solo usuario local, sin login y sin acceso por LAN.
- CP fijo 22002 y almacén 4389; no se configuran desde la UI.
- Menú solo de comida y cena, sin recetas ni pasos de cocina.
- El catálogo depende de la API no oficial de Mercadona; si cambia, la sync
  puede fallar y se conserva la última copia válida.
- Los alérgenos se filtran fail-closed: si un producto no tiene datos
  suficientes, se excluye cuando el usuario declara alérgenos.
- No se automatiza la compra ni se guardan credenciales.

## Aviso

Cesta no está afiliada a Mercadona. Los precios y la disponibilidad son los de la
tienda online para el CP 22002 (almacén 4389) y pueden cambiar. La app no sustituye
el etiquetado oficial de alérgenos: confirma siempre el envase. Los menús
guardados conservan su snapshot; revalida antes de comprar si los precios han
cambiado.
