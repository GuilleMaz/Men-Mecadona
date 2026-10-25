# Decisions

## 2026-10-25 — shadcn/ui por copia, sin CLI interactivo

### Problema

El CLI de shadcn no completa `init` en este entorno sin TTY: la versión actual escribe `components.json` y después falla con «Could not load the workspace config»; la versión anterior pide confirmación interactiva para reinstalar componentes.

### Decisión

- Mantener `components.json` con `style: new-york`, Tailwind 4 y alias `@/*`.
- Copiar el código canónico de shadcn para `button`, `card`, `input` y `label`, con `clsx`, `tailwind-merge`, `class-variance-authority`, `@radix-ui/react-slot` y `@radix-ui/react-label`.
- Definir el tema en `src/index.css` con variables oklch y primario verde (Cesta); sin modo oscuro en el MVP.
- Usar `new-york` (compatible con Tailwind 4) para que futuras incorporaciones mantengan el mismo estilo que estos componentes.

### Justificación

- shadcn/ui se basa en copiar componentes; el CLI no es un requisito en ejecución.
- Evita depender de prompts, de un TTY y de un fallo del CLI.
- Los componentes quedan versionados, revisables y sin dependencia de una librería UI empaquetada.

### Alternativas

- `--force` / `--legacy-peer-deps`: no resuelve los prompts ni el error de workspace.
- MUI, Chakra u otra librería empaquetada: descartadas por stack, peso y estilo.
- Dejar el frontend sin shadcn: incumple el stack acordado.

---

## 2026-10-25 — Backend plano gestionado con uv

### Problema

`backend/` debía arrancar con Python 3.13, un lockfile reproducible y sin empaquetar la app como distribución instalable.

### Decisión

- `uv` con `requires-python = ">=3.13,<3.14"`, `.python-version` y `uv.lock` versionado.
- `[tool.uv] package = false`: `app/` es un paquete de aplicación, no una distribución. Se ejecuta con `uv run` desde `backend/`.
- pytest resuelve `app` con `pythonpath = ["."]`; mypy se ejecuta sobre `app` desde `backend/`.
- Dependencias de desarrollo en `[dependency-groups] dev` (PEP 735), no en `project.optional-dependencies`.
- CORS se configura a nivel de app (`create_app`) y solo con `allow_credentials=False`: no hay cookies entre orígenes en un MVP local.

### Justificación

- Reproducibilidad sin publicar paquetes.
- Evita `src/` y `__init__.py` innecesarios en tests.
- Un único comando (`uv sync`) deja el entorno listo.

### Alternativas

- Proyecto instalable con build backend: descartado; añade pasos y artefactos sin beneficio para una app local.
- `venv` + `pip` + `requirements.txt`: descartado; menos reproducible que `uv.lock`.
- `allow_credentials=True`: innecesario y más permisivo.

---

## 2026-10-25 — Menú sin recetas

### Problema

El usuario quiere un menú basado en productos de Mercadona, no un recetario con pasos de cocina.

### Decisión

El dominio usa **platos** (`dishes`) con nombre, composición de ingredientes/productos y etiquetas. No hay pasos, tiempos de elaboración ni instrucciones. La UI no llama “receta” a un plato.

### Justificación

- Reduce alcance y mantenimiento.
- El valor está en el menú, el coste y la lista de la compra.
- Evita depender de contenido culinario extenso.

### Alternativas

- Recetario completo con pasos: descartado por petición explícita.
- Menú solo de productos sin platos: descartado por combinaciones incoherentes.

---

## 2026-10-25 — FastAPI + React + SQLite + CP-SAT

### Problema

Elegir stack y motor de optimización para una app local.

### Decisión

FastAPI + Python para backend; React + Vite + TypeScript para frontend; SQLite para persistencia; OR-Tools CP-SAT para optimización.

### Justificación

- FastAPI encaja con el optimizador y genera OpenAPI.
- React permite una rejilla de menú interactiva.
- SQLite es suficiente para un usuario y ~4.000 productos.
- CP-SAT modela paquetes, presupuesto y variedad con variables enteras.

### Alternativas

- Streamlit: descartado por petición explícita y limitaciones de interacción.
- HTMX: viable, pero menos fluido para edición de menús.
- Next.js: descartado para mantener Python en el backend.
- Postgres/Redis/Celery: sobredimensionado para local.
- Greedy/local search: menos fiable con presupuesto y paquetes.

---

## 2026-10-25 — Contrato de presupuesto

### Problema

No estaba claro si el presupuesto era duro o se podía relajar al mostrar el menú mínimo.

### Decisión

Todo menú **guardado y presentado como válido** tiene ticket ≤ presupuesto. Si el mínimo lo supera, se devuelve `status="infeasible"` con un preview marcado, `minimum_ticket_cents`, `shortfall_cents` y sugerencias; `menu_id=null`, no se persiste y no genera lista oficial.

### Justificación

- Evita que un menú inválido se presente como válido.
- Permite enseñar el mínimo sin romper la promesa.
- Da un contrato único para frontend, tests y solver.

### Alternativas

- Relajar el presupuesto y devolver el menú mínimo como válido: descartado.
- Devolver solo un error sin preview: peor UX.

---

## 2026-10-25 — Identidad contable

### Problema

Ticket, consumo, despensa y sobras no cuadraban; el ejemplo inicial era aritméticamente imposible.

### Decisión

Formalizar:

```text
ticket + pantry_consumption = consumption + leftover
```

- `ticket`: paquetes comprados.
- `consumption`: valor de todo lo usado, incluida la despensa.
- `pantry_consumption`: valor de la despensa usada.
- `leftover`: `ticket − (consumption − pantry_consumption)`.
- La lista de la compra suma exactamente `ticket`.

### Justificación

- La propuesta de valor es el coste real.
- Permite tests verificables.
- Evita cifras que no se pueden explicar en la UI.

### Alternativas

- Mostrar solo consumo: irreal.
- Mostrar solo ticket: no compara platos.
- Valorar sobras “durables” sin vida útil: descartado; queda en backlog.

---

## 2026-10-25 — Optimizador lexicográfico

### Problema

Un objetivo escalar con penalizaciones podía violar variedad aunque existiera un menú variado factible.

### Decisión

Dos etapas:

1. Minimizar la suma de violaciones de variedad con presupuesto duro.
2. Fijar esa suma y minimizar el ticket.

Las reglas y umbrales están en `PLAN.md` §6.6; todas las violaciones pesan 1. Si la etapa 1 no prueba optimalidad, se usa el incumbente, se mejora en la etapa 2 y se devuelve `feasible`, nunca `optimal`.

La demanda se calcula por plato:

```text
coef[r,i] = round(quantity_milli[r,i] × people / base_servings[r])
need_i(x) = Σ coef[r,i] × x[r,d,s]
```

Si el presupuesto es infeasible, resolver sin presupuesto para obtener el mejor ticket posible y devolver preview `infeasible` con `minimum_is_estimate` si no se prueba optimalidad.

### Justificación

- Garantiza “el menú más barato que cumple variedad” cuando es posible.
- Si no es posible, devuelve el mínimo de violaciones y lo explica.
- Evita pesos mágicos y resultados no demostrables.
- La fórmula de demanda depende de la selección real de platos.

### Alternativas

- Penalización escalar única: descartada por riesgo de violar variedad.
- Relajación en cascada con múltiples solves: más lenta y ambigua.
- `need_milli` constante: descartada; compraría para un menú no elegido.

---

## 2026-10-25 — Unidades enteras y producto único

### Problema

Las raciones escaladas producían fracciones y un producto podía contarse en dos ingredientes.

### Decisión

- Cantidades en milésimas de unidad base (mg, µl, mili-unidades).
- Costes en céntimos enteros.
- `UNIQUE(product_id)` en `ingredient_products`: un producto = un ingrediente.
- `coef[r,i]` se redondea por plato antes de multiplicar por `x`.
- `used` y `leftover` se calculan después de resolver; no son variables del solver.
- Consumo asignado a los formatos comprados de menor precio unitario primero.

### Justificación

- CP-SAT exige coeficientes enteros.
- Evita doble conteo de oferta.
- Hace reproducible el coste y la demanda.

### Alternativas

- Redondeo ad hoc: descartado.
- `y[p,i]` con producto multi-ingrediente: más complejo; queda para escala.
- `used`/`leftover` como variables: descartado; no aportan al objetivo y complican el modelo.

---

## 2026-10-25 — Alérgenos fail-closed

### Problema

El filtrado de alérgenos no era garantizable con el modelo anterior.

### Decisión

- Lista canónica: gluten, crustaceans, eggs, fish, peanuts, soybeans, milk, nuts, celery, mustard, sesame, sulphites, lupin, molluscs y `unknown`.
- `products.allergen_status ∈ {known, partial, unknown}` y `product_allergens` con origen y confianza.
- `P_i` solo incluye productos `known` sin alérgenos declarados por el usuario.
- `partial`/`unknown` se excluyen si el usuario declara alérgenos; si `P_i` queda vacío, el ingrediente y sus platos son inelegibles.
- La unión ingrediente/producto es la fuente de verdad.
- Producto de respaldo = siguiente elegible por prioridad.
- Los alérgenos son un campo estricto, separado de “no me gusta”.
- Tests para los 14 códigos, `unknown`, producto de respaldo y presión de presupuesto.

### Justificación

- Es un requisito de seguridad y legal.
- “Cuando sea posible” no es aceptable para alérgenos.
- La ausencia de filas no puede confundirse con “sin alérgenos”.

### Alternativas

- Confiar solo en etiquetas de ingrediente: insuficiente.
- Permitir al usuario eliminar alérgenos: descartado.
- Filtrar solo a nivel de plato: insuficiente si el producto elegido cambia.

---

## 2026-10-25 — CP fijo 22002 / almacén 4389 en el MVP

### Problema

El CP aparecía como configurable en unos documentos y fijo en otros.

### Decisión

El MVP usa **CP 22002 / almacén 4389**. No hay cambio de CP desde la UI. Si no se confirma el almacén, no se genera menú. La copia local solo se usa si su `warehouse=4389` y `postal_code=22002`; sirve para consultar menús guardados, no para generar nuevos.

### Justificación

- Reduce alcance y evita precios de otra zona.
- El usuario indicó 22002.
- El cambio de CP queda en backlog.

### Alternativas

- CP configurable con re-sync y invalidación de menús: más complejo; backlog.

---

## 2026-10-25 — SQLite fuera de OneDrive

### Problema

La base de datos vivía bajo OneDrive, con riesgo de locks y corrupción de WAL.

### Decisión

Guardar la base en `%LOCALAPPDATA%\Cesta\cesta.db`. `CESTA_DATA_DIR` es opcional y, si se define, debe ser una ruta absoluta; el valor por defecto se calcula en `config.py` desde `os.environ["LOCALAPPDATA"]`. Activar WAL, `foreign_keys=ON` y `busy_timeout=5000`. Backup con la app parada.

### Justificación

- Evita sincronización de `-wal` y `-shm`.
- Protege el único dato persistente del usuario.
- Mantiene portabilidad local.

### Alternativas

- Mantener `data/` en OneDrive: descartado.
- Postgres local: sobredimensionado.

---

## 2026-10-25 — Despensa por cantidades

### Problema

“Tengo suficiente” y “cantidad” eran modelos incompatibles.

### Decisión

`pantry_items` guarda `quantity_milli` por ingrediente en unidad base, sin columna `unit` duplicada. La UI ofrece “tengo suficiente” como atajo que fija la cantidad del snapshot del menú a la necesidad actual; no modifica la despensa global. `net_need = max(0, need − pantry)` antes de calcular paquetes.

### Justificación

- Representa el caso normal: media botella de aceite.
- Evita paquetes negativos y sobrecompra.
- Permite tests parciales.

### Alternativas

- Booleano “tengo”: demasiado grueso.
- Solo cantidades exactas sin atajo: peor UX.

---

## 2026-10-25 — Simplificación del MVP

### Problema

El plan inicial incluía elementos que no aportaban al núcleo y aumentaban el riesgo.

### Decisión

Quitar del MVP: `price_snapshots`, `raw_json` persistente, APScheduler, Recharts, Playwright y el fallback dual SciPy/PuLP. Mantener un solo solver tras el spike F0.6.

### Justificación

- Menos superficie de error y mantenimiento.
- El historial de precios y el E2E quedan en backlog.
- El stack sigue siendo suficiente.

### Alternativas

- Mantener todo: más alcance y deuda antes de validar el núcleo.

---

## 2026-10-25 — Alcance móvil

### Problema

“Usable en móvil durante la compra” chocaba con `127.0.0.1`.

### Decisión

El MVP es local en escritorio/tableta. La compra se lleva con lista imprimible/exportable. El acceso por LAN desde el móvil queda en backlog con autenticación.

### Justificación

- Evita exponer la app sin auth.
- Mantiene el modelo local seguro.
- Cubre el caso de uso con impresión/exportación.

### Alternativas

- Bind a `0.0.0.0` sin auth: descartado.
- PWA: backlog.

---

## 2026-10-25 — Identificadores en inglés, UI en español

### Problema

Los tags y slugs mezclaban idiomas y contradecían “código en inglés”.

### Decisión

Slugs, enums y tags de dominio en inglés (`lunch`, `dinner`, `chicken`, `beef`). Nombres y textos de UI en español. La UI traduce etiquetas.

### Justificación

- Consistencia de código.
- Evita errores de búsqueda y validación.
- Mantiene la experiencia en español.

### Alternativas

- Tags en español: aceptable, pero contradice la convención; descartado.

---

## 2026-10-25 — Plan de compra canónico

### Problema

F3 prometía un ticket exacto y F4 usaba variables del solver; el preview y la lista podían no coincidir.

### Decisión

`plan_purchase(ingrediente, necesidad_neta)` elige la combinación de paquetes que minimiza `Σ q × precio` sujeto a `Σ q × cantidad_paquete ≥ necesidad_neta`. Permite mezclar formatos y desempata por menos paquetes, menor precio y `product_id`. F3 y F4 comparten esta función. F4 usa `q` para el presupuesto y materializa la lista final con `plan_purchase`; se verifica `ticket_canónico ≤ ticket_solver ≤ budget`.

### Justificación

- Elimina dos criterios de compra incompatibles.
- Garantiza `preview.ticket == shopping_list.ticket`.
- Mantiene el presupuesto como límite duro.

### Alternativas

- Recalcular la lista con `ceil` sobre el producto por defecto: descartado; podía superar el presupuesto.
- Usar solo el plan del solver y un preview distinto: descartado.

---

## 2026-10-25 — Contrato de estados y preview

### Problema

Se mezclaban estados de generación, estados persistidos, errores HTTP y `stale`.

### Decisión

- Generación: `optimal`, `feasible`, `relaxed`, `infeasible`, `timeout`.
- Persistido: `optimal`, `feasible`, `relaxed`; `timed_out` aparte.
- `price_status`: `current` o `stale`, independiente del estado de generación.
- `infeasible` solo para presupuesto: `is_preview=true`, `menu_id=null`, `minimum_ticket_cents`, `minimum_is_estimate`, `shortfall_cents`, sin persistencia.
- `NO_FEASIBLE_MENU` 422 para repeticiones, mínimos, bloqueos o asignación.
- `no_eligible_dishes` solo 422.
- `timeout` con mejor esfuerzo se persiste como `feasible` + `timed_out=true`.

### Justificación

- Frontend, tests y solver comparten un único contrato.
- Evita presentar un preview como menú válido.
- Permite distinguir precios obsoletos de una solución inválida.

### Alternativas

- Un solo estado `stale`: descartado; perdía la procedencia.
- `infeasible` para cualquier causa: descartado; mezclaba presupuesto con bloqueos.

---

## 2026-10-25 — Mínimos y variedad operacionalizados

### Problema

“150 g de verdura”, “límite de carne roja” y “cenas ligeras” no tenían unidad, umbral ni definición de violación.

### Decisión

- Mínimos por persona y día: 1 ración de verdura (150 g), 1 de proteína (100 g carne/pescado, 2 huevos, 80 g legumbre seca o 200 ml lácteo) y 1 de hidrato (60 g arroz/pasta secos, 150 g patata o 60 g pan).
- Los ingredientes declaran `serving_group` y `serving_size_milli`.
- Variedad: proteína `min(3, days)`, pescado `ceil(days/7)`, legumbres `ceil(days/7)`, carne roja `ceil(days×3/7)`, cenas ligeras `ceil(days/2)`, hidratos `min(2, days)`.
- Todas las violaciones pesan 1.
- `light` = sin carne roja, ≥1 ración de verdura y ≤1 ración de hidrato.

### Justificación

- Hace el modelo y los tests implementables.
- Evita tags subjetivos.
- Mantiene el equilibrio por grupos, no calorías.

### Alternativas

- Tags booleanos sin cantidades: descartado; no verificable.
- Calorías/macros: fuera de alcance del MVP.

---

## 2026-10-25 — Copia local solo para consulta

### Problema

Se podía usar una copia local de otro almacén para generar menús y mostrar precios incorrectos.

### Decisión

La copia local solo se usa si su `warehouse=4389` y `postal_code=22002`. Sirve para consultar menús guardados; no permite generar menús nuevos mientras la API no confirme el almacén. Si es de otro almacén, no se usa.

### Justificación

- Evita mezclar precios de zonas distintas.
- Mantiene la promesa de precios de 22002/4389.

### Alternativas

- Usar la copia con aviso: descartado; el presupuesto sería engañoso.
- Bloquear toda la app sin red: peor UX; se permite consultar.
