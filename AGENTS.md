# AGENTS.md — Cesta

> Guía operativa para agentes que trabajen en este repositorio.
> **Estado actual:** F1 completada el 2026-10-26 (F1.1-F1.8). Siguiente fase: F2.
> **Última actualización:** 2026-10-26

---

## 1. Lectura obligatoria

Antes de tocar nada:

1. `PLAN.md` — alcance, contratos y reglas de negocio.
2. `TASKS.md` — fase actual y tareas accionables.
3. `project-memory/project-overview.md`
4. `project-memory/architecture.md`
5. `project-memory/decisions.md`
6. `project-memory/next-steps.md`
7. `project-memory/changelog.md`

`PLAN.md` es la fuente de alcance. `TASKS.md` es la fuente de ejecución. `project-memory/` es el estado. No dupliques reglas en nuevos documentos.

---

## 2. Producto

**Cesta** es una app web local que genera un menú de **comidas y cenas** para N personas, N días (1-14) y un presupuesto total, usando productos y precios de la tienda online de Mercadona.

- Entrada: personas, días, presupuesto.
- Salida: menú de `días × 2` comidas, coste y lista de la compra.
- **Sin recetas ni pasos de cocina.** El dominio usa **platos** (`dishes`).
- Precios: CP **22002**, almacén **4389**.
- Presupuesto: **límite máximo duro sobre el ticket**.
- Nutrición: equilibrio por grupos, no calorías.
- Sin dieta especial por defecto; sí exclusiones y alérgenos.
- Local, sin login, en `127.0.0.1`.

---

## 3. Invariantes que no se negocian

1. **Solo comida y cena.** Nada de desayuno, merienda o snacks.
2. **Sin recetas ni pasos.** No uses `recipe` en código, rutas, esquemas ni UI.
3. **Todo menú guardado y presentado como válido tiene ticket ≤ presupuesto.**
4. **Si el mínimo no cabe**, se devuelve un preview `infeasible` con mínimo, déficit y sugerencias; **no se guarda** como menú válido ni genera lista oficial.
5. **Nunca relajar alérgenos, dieta o exclusiones** para cuadrar el presupuesto.
6. **Alérgenos fail-closed:** si el usuario declara un alérgeno y un producto es `unknown`, no es elegible.
7. **Precios de Mercadona online**, CP 22002 / almacén 4389. No inventar precios, productos ni disponibilidad.
8. **No automatizar la compra** ni manejar credenciales.
9. **No usar `float` para dinero.** `Decimal` en dominio; céntimos enteros en solver.
10. **No mezclar almacenes.** Si no se confirma 4389, no se genera menú.
11. **La lista de la compra suma exactamente el ticket.**
12. **Un producto pertenece a un único ingrediente canónico.**
13. **Nada de Streamlit.**

---

## 4. Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.13 + FastAPI + Uvicorn |
| Validación | Pydantic v2 + pydantic-settings |
| ORM | SQLAlchemy 2 + Alembic |
| Base de datos | SQLite WAL en `%LOCALAPPDATA%\Cesta` |
| HTTP | httpx + tenacity |
| Optimizador | OR-Tools CP-SAT |
| Frontend | React 19 + Vite + TypeScript |
| Estilos | Tailwind CSS 4 + shadcn/ui |
| Estado servidor | TanStack Query |
| Rutas | React Router |
| Formularios | React Hook Form + Zod |
| Iconos | Lucide |
| Tests backend | pytest + respx |
| Tests frontend | Vitest + Testing Library + MSW |
| Tooling | uv, Ruff, mypy, npm, ESLint, Prettier |

**No añadir** Postgres, Redis, Celery, Docker, Next.js, APScheduler, Recharts, Playwright ni una librería de UI pesada sin justificarlo y actualizar `project-memory/decisions.md`.

---

## 5. Estructura prevista

```text
MERCADONA/
├── PLAN.md
├── TASKS.md
├── AGENTS.md
├── project-memory/
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── api/
│   │   ├── services/
│   │   │   ├── mercadona_client.py
│   │   │   ├── catalog_sync.py
│   │   │   ├── pricing.py
│   │   │   ├── optimizer.py
│   │   │   ├── menu_service.py
│   │   │   └── seed.py
│   │   └── data/
│   │       ├── ingredients.yaml
│   │       └── dishes.yaml
│   └── tests/
├── frontend/
│   └── src/
├── scripts/
├── run.ps1
├── check.ps1
├── finish-phase.ps1
└── .env.example
```

No crear carpetas vacías “por si acaso”. La estructura se materializa en F0.

---

## 6. Comandos previstos

```powershell
# Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run ruff check .
uv run mypy app

# Frontend
cd frontend
npm install
npm run dev
npm run test
npm run lint
npm run build

# Todo
.\run.ps1
.\run.ps1 -Prod

# Calidad y cierre de fase
.\check.ps1
.\finish-phase.ps1 -Phase F0 -Summary "fundaciones y spikes"
```

`finish-phase.ps1` es el gate de cierre: ejecuta `check.ps1`, rechaza secretos,
bases de datos y dependencias, hace el commit `FASE: resumen` y lo sube a GitHub.
No se cierra una fase sin este paso salvo que el usuario lo impida explícitamente.

Si PowerShell bloquea el script:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Si un comando no existe, créalo en la tarea correspondiente; no afirmes que funciona.

---

## 7. Convenciones

### Python

- Python 3.13, type hints en funciones públicas.
- Ruff para lint y formato; línea máxima 100.
- mypy razonable; evitar `Any` sin justificación.
- Pydantic v2 para esquemas.
- SQLAlchemy 2 declarativo.
- Servicios puros y dependencias inyectadas.
- Errores de dominio con códigos estables.
- Nada de lógica de negocio en routers.
- Nada de SQL en componentes de UI.

### Dinero y unidades

- `Decimal` para precios; nunca `float`.
- Céntimos enteros en base de datos y solver.
- Cantidades en milésimas de unidad base: mg, µl o mili-unidades.
- `quantity_milli`, `package_quantity_milli`, `package_price_cents`.
- `unit_price` de Mercadona es precio del **paquete**, no precio por unidad base.
- No guardar “precio por gramo” en céntimos; calcular desde precio y cantidad del paquete.
- Redondear paquetes con `ceil` después de restar despensa.
- Consumo y sobras se calculan con `Decimal` y se redondean half-up al final.

### Frontend

- TypeScript estricto.
- Componentes funcionales y pequeños.
- TanStack Query para estado de servidor; no Redux.
- React Hook Form + Zod.
- Tailwind + shadcn/ui.
- Textos de UI en español; identificadores de dominio en inglés.
- Accesibilidad: labels, foco, teclado, contraste.
- No mostrar pasos de cocina ni llamar “receta” a un plato.

### API

- Prefijo `/api`.
- JSON tipado y errores homogéneos:

```json
{
  "error": {
    "code": "CODE",
    "message": "Mensaje para el usuario",
    "details": {}
  }
}
```

- Paginación explícita en listados.
- No exponer `raw_json` ni detalles internos.
- No romper contratos sin actualizar frontend, tests y PLAN.

### Base de datos

- Migraciones Alembic; nada de cambios manuales.
- SQLite WAL, `foreign_keys=ON`, `busy_timeout=5000`.
- `render_as_batch=True` para SQLite.
- Constraints únicos y CHECKs.
- Seed reproducible desde YAML.
- No versionar `cesta.db`, `-wal` ni `-shm`.

---

## 8. Contratos clave

### Presupuesto

- `POST /api/menus/generate` devuelve `status` tipado y `is_preview`.
- `optimal`, `feasible`, `relaxed`: menú persistido y `ticket ≤ budget`.
- `infeasible`: `is_preview=true`, `menu_id=null`, `reason="budget"`, `minimum_ticket_cents`, `minimum_is_estimate`, `shortfall_cents`; no persistido.
- `NO_FEASIBLE_MENU` (422) para `repeats`, `minimums`, `locks` o `no_assignment`.
- `no_eligible_dishes`: 422, no estado de menú.
- `timeout` con mejor esfuerzo se persiste como `feasible` + `timed_out=true`; sin mejor esfuerzo, `menu_id=null`.
- `price_status` (`current|stale`) es independiente del estado de generación.
- Un swap que supera presupuesto devuelve `BUDGET_EXCEEDED` y no se aplica.
- “Ya lo tengo” que supera presupuesto también se rechaza.

### Coste

- Identidad obligatoria: `ticket + pantry_consumption = consumption + leftover`.
- `shopping_items` suma exactamente `ticket`.
- `Σ menu_entry_ingredients.consumption = Σ entries.consumption = menus.consumption`.
- La despensa se valora al coste unitario del formato elegible más barato; si no hay compra, al producto por defecto.
- `plan_purchase` es la función canónica de compra; F3 y F4 la comparten.
- La lista se deriva de `plan_purchase`; no se recalcula con otro criterio.
- Cualquier mutación o revalidación recalcula ticket, lista y costes por entrada en la misma transacción.

### Alérgenos

- Lista canónica: gluten, crustaceans, eggs, fish, peanuts, soybeans, milk, nuts, celery, mustard, sesame, sulphites, lupin, molluscs, `unknown`.
- `products.allergen_status ∈ {known, partial, unknown}`; `product_allergens` con origen y confianza.
- `P_i` solo incluye productos `known` sin alérgenos declarados por el usuario.
- `partial`/`unknown` se excluyen si el usuario declara alérgenos.
- Unión ingrediente/producto; si `P_i` queda vacío, el ingrediente y sus platos son inelegibles.
- Producto de respaldo = siguiente elegible por prioridad.
- No se pueden eliminar desde “no me gusta”.
- Aviso legal visible.

### Despensa

- Por ingrediente y `quantity_milli` en unidad base; sin columna `unit` duplicada.
- `net_need = max(0, need - pantry)` antes de `ceil`.
- La despensa no se descuenta del consumo; se contabiliza aparte.
- “Tengo suficiente” modifica el snapshot del menú, no la despensa global.

### Optimizador

- Unidades enteras, costes en céntimos.
- `coef[r,i] = round(quantity_milli[r,i] × people / base_servings[r])`.
- Demanda: `Σ q[p] × package_quantity_milli[p] + pantry ≥ Σ coef[r,i] × x[r,d,s]`.
- Etapa 1: minimizar `Σ violation[k]`; etapa 2: fijar la suma y minimizar ticket.
- Presupuesto, repeticiones y bloqueos duros.
- `used`/`leftover` son post-cálculo, no variables.
- Si la etapa 1 no prueba optimalidad, devolver `feasible`, nunca `optimal`.
- `num_search_workers=1` y semilla fija para tests.
- Tiempo total del solver 8 s; generación p95 < 10 s.

### Integración Mercadona

- CP fijo 22002; almacén 4389.
- `PUT /api/postal-codes/actions/change-pc/`; leer `x-customer-wh`.
- `?wh=4389` en catálogo.
- Sync por subcategoría con estado parcial.
- Concurrencia máxima 4; reintentos con backoff.
- No guardar el catálogo completo en el repo.
- Si no se confirma 4389, no generar menú.
- La copia local solo se usa si su `warehouse=4389` y `postal_code=22002`; sirve para consultar menús guardados, no para generar nuevos.

---

## 9. Tests

- Sin llamadas reales a Mercadona.
- Fixtures mínimas y sintéticas; no commitear el catálogo completo.
- Tests de coste con casos dorados.
- Test de identidad contable.
- Test de optimalidad con fuerza bruta en instancia pequeña.
- Test de demanda con platos de distinto `base_servings` que comparten ingrediente.
- Test `preview.ticket == shopping_list.ticket`.
- Tests de alérgenos, despensa parcial, sync parcial y swap caro.
- Tests de mínimos y variedad en 1/2/7/14 días.
- Tests de exportación y escape de fórmulas CSV.
- Test de privacidad: sin telemetría ni llamadas externas no declaradas.
- Tests de API con base SQLite temporal.
- Tests de frontend con MSW.
- Un cambio de lógica de negocio requiere test.
- Un bug se corrige con un test que lo reproduzca.

---

## 10. Memoria del proyecto

Usar la skill `memory-keeper`.

Al empezar:

1. Leer `project-memory/`.
2. Comprobar `TASKS.md`.
3. Verificar el estado real del repo.

Al terminar una tarea:

1. Actualizar `project-memory/changelog.md`.
2. Actualizar `project-memory/next-steps.md`.
3. Si hubo decisión técnica, `decisions.md`.
4. Si cambió la estructura, `architecture.md`.
5. Marcar la tarea en `TASKS.md`.
6. Cerrar la fase con `.\finish-phase.ps1 -Phase Fx -Summary "..."`.

No dupliques información: `PLAN.md` alcance, `TASKS.md` ejecución, `project-memory` estado.

---

## 11. Flujo de trabajo

1. Leer documentación y memoria.
2. Identificar la tarea actual en `TASKS.md`.
3. Proponer un plan corto si hay ambigüedad.
4. Implementar solo esa tarea.
5. Añadir tests.
6. Ejecutar lint, tipos y tests.
7. Actualizar `TASKS.md` y `project-memory`.
8. Cerrar la fase con `.\finish-phase.ps1 -Phase Fx -Summary "..."`.
9. Reportar qué se hizo, qué se verificó, el commit y qué queda.

Reglas:

- No implementar fases futuras “de paso”.
- No cambiar el alcance sin confirmación.
- No borrar trabajo existente sin investigarlo.
- No dejar TODOs sin registrar en `next-steps.md`.
- No commitear secretos, base de datos ni `node_modules`.
- No usar `git` para descartar cambios del usuario.
- No cerrar una fase sin commit y push a GitHub, salvo bloqueo explícito del usuario.

---

## 12. Definition of Done

Una tarea está terminada cuando:

- cumple su DoD de `TASKS.md`;
- tiene tests o validación equivalente;
- pasa lint, tipos y tests en verde;
- no rompe fases anteriores;
- la UI (si aplica) es responsive y accesible;
- no hay telemetría ni llamadas externas no declaradas;
- `TASKS.md` está actualizado;
- `project-memory/changelog.md` y `next-steps.md` están actualizados;
- el README o la documentación reflejan cambios relevantes;
- la fase está commiteada y subida a GitHub con `finish-phase.ps1`, o existe un bloqueo explícito documentado.

---

## 13. Prohibiciones

- No crear recetas ni pasos de cocina.
- No usar Streamlit.
- No usar `float` para dinero.
- No hardcodear precios o productos.
- No llamar a Mercadona en tests.
- No automatizar la compra.
- No añadir login en el MVP.
- No inventar disponibilidad.
- No relajar alérgenos.
- No devolver un menú que supere el presupuesto sin marcarlo como preview inválido.
- No mezclar precios de almacenes.
- No exponer `raw_json`.
- No mezclar cambios de varias fases.
- No duplicar documentación que contradiga `PLAN.md`.
