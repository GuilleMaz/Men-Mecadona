# Cesta

Aplicación web local que genera un menú de **comidas y cenas** para N personas,
N días y un presupuesto, con productos y precios de la tienda online de Mercadona.
Sin recetas ni pasos de cocina: cada plato es una ficha con composición y etiquetas.

> Estado: F0 completada (fundaciones y spikes). El catálogo persistente y el
> optimizador llegan en F1 y F4. La documentación de alcance está en `PLAN.md` y
> el detalle de ejecución en `TASKS.md`.

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
4. Arranca el backend en `http://127.0.0.1:8000`.
5. Arranca el frontend en `http://localhost:5173`.

Para detener ambos servicios, pulsa `Ctrl+C`.

## Calidad

```powershell
.\check.ps1
```

Ejecuta Ruff, mypy y pytest en backend; ESLint, Prettier, TypeScript, Vitest y
build en frontend; y Ruff sobre los scripts de Python de la raíz.

## Cierre de fase

Cada fase se cierra con un único comando:

```powershell
.\finish-phase.ps1 -Phase F1 -Summary "catalogo y sincronizacion"
```

El script ejecuta `check.ps1`, rechaza secretos, bases de datos, `node_modules` y
`.venv`, crea el commit `F1: catalogo y sincronizacion` y lo sube a GitHub. Si la
calidad falla, no se hace commit. Si el push falla, el commit queda local y el
script termina con error para poder reintentarlo.

## Estructura

```text
backend/    FastAPI + SQLite + OR-Tools
frontend/   React + Vite + TypeScript
scripts/    spikes y utilidades manuales
```

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
