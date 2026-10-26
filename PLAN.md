# PLAN.md — Cesta

> **Estado:** F3 completada el 2026-10-26. Siguiente fase: F4 (optimizador, menú y lista de la compra).
> **Última actualización:** 2026-10-26
> **Nombre provisional:** Cesta
> **Ubicación:** `C:\Users\guill\OneDrive\Escritorio\OpenCode\MERCADONA`

---

## 1. Resumen ejecutivo

**Cesta** es una aplicación web local que genera un menú de **comidas y cenas** para un número de personas, un número de días y un presupuesto total, usando productos y precios de la tienda online de Mercadona.

El usuario indica personas, días y presupuesto. La app devuelve:

- un menú de `días × 2` comidas;
- el coste real;
- la lista de la compra con paquetes y precios;
- opciones para cambiar, bloquear o excluir platos.

**No hay recetas ni pasos de cocina.** Cada plato es una ficha con nombre, composición de productos y etiquetas. La UI muestra el plato y sus productos, nunca instrucciones de elaboración.

### Contrato económico

Se separan dos métricas:

- **Coste de consumo:** valor de lo que se usa, incluida la despensa.
- **Ticket de compra:** lo que se paga en caja por paquetes cerrados.

El presupuesto es un **límite máximo duro sobre el ticket**. Un menú guardado y presentado como válido nunca lo supera.

Si ni siquiera el menú más barato cabe, se devuelve un **preview de inviabilidad** claramente marcado, con el mínimo necesario y el déficit. Ese preview **no se guarda** como menú válido y no genera una lista de la compra “oficial”.

---

## 2. Alcance

### 2.1 Incluido en el MVP

- Menú de **comida y cena** únicamente.
- **Sin recetas ni pasos.** Dominio de **platos** (`dishes`), no de recetas.
- Formulario inicial: personas (1-10), días (1-14), presupuesto total.
- Catálogo inicial de **50-60 platos** y ~120 ingredientes.
- Precios de Mercadona online para **CP 22002 / almacén 4389**.
- Presupuesto como límite máximo; menú más barato que cumpla variedad y equilibrio.
- Exclusiones persistentes por ingrediente, plato y etiqueta.
- Alérgenos estrictos con política *fail-closed*.
- Despensa por cantidades en unidad base.
- Lista de la compra consolidada, con paquetes, precios y checkboxes.
- Cambio de plato, bloqueo y regeneración.
- Historial simple de menús guardados.
- Exportación/impresión de la lista.
- Funcionamiento local, sin login.

### 2.2 Fuera de alcance del MVP

- Recetas, pasos, tiempos de cocina o modo chef.
- Desayunos, meriendas y snacks.
- Compra online, carrito o checkout.
- Multiusuario, nube o sincronización entre dispositivos.
- Macros, calorías o planes nutricionales clínicos.
- Productos de limpieza, higiene, bebé, mascotas o parafarmacia.
- Precios de tienda física.
- App móvil nativa.
- Cambio de código postal desde la UI.
- Acceso desde el móvil por LAN.
- Comparación con otros supermercados.

---

## 3. Requisitos

### 3.1 Funcionales

| ID | Requisito | Prioridad |
|---|---|---|
| RF-01 | La pantalla inicial pide personas, días y presupuesto total. | Must |
| RF-02 | El menú contiene exactamente `días × 2` huecos: comida y cena. | Must |
| RF-03 | Todo menú guardado y presentado como válido tiene ticket ≤ presupuesto. | Must |
| RF-04 | Si el mínimo supera el presupuesto, se devuelve un preview `infeasible` con mínimo, déficit y sugerencias; no se guarda como válido. | Must |
| RF-05 | Se pueden excluir ingredientes, platos y etiquetas; la exclusión persiste. | Must |
| RF-06 | Los alérgenos se filtran de forma estricta y *fail-closed*; nunca se relajan. | Must |
| RF-07 | El menú muestra platos y productos; no muestra pasos de cocina. | Must |
| RF-08 | La lista de la compra consolida productos, paquetes y total. | Must |
| RF-09 | La despensa resta necesidad antes de calcular paquetes. | Must |
| RF-10 | Se pueden cambiar platos, bloquearlos y regenerar el resto. | Must |
| RF-11 | Cada menú muestra fecha, código postal y almacén de los precios. | Must |
| RF-12 | El catálogo se sincroniza al arrancar y se puede refrescar manualmente. | Must |
| RF-13 | Los menús se guardan y se pueden consultar en el historial. | Should |
| RF-14 | Se pueden buscar platos y productos. | Should |
| RF-15 | Se muestra coste por comida, por día y por persona. | Must |
| RF-16 | La lista de la compra se puede imprimir o exportar. | Should |
| RF-17 | El menú cumple mínimos diarios de verdura, proteína e hidratos y variedad de fuentes. | Must |
| RF-18 | El MVP usa CP 22002 / almacén 4389; el cambio de CP queda para el backlog. | Must |
| RF-19 | Se muestra el valor total de los productos que sobran. | Should |
| RF-20 | El sistema valida que todos los platos e ingredientes tienen producto, precio y unidades coherentes. | Must |
| RF-21 | Un producto pertenece a un único ingrediente canónico. | Must |
| RF-22 | La identidad contable ticket/consumo/despensa/sobras se cumple y se testea. | Must |
| RF-23 | Los cambios manuales recalculan ticket y lista, y no pueden romper el presupuesto. | Must |

### 3.2 No funcionales

| ID | Requisito |
|---|---|
| RNF-01 | Funcionamiento local en `127.0.0.1`, sin autenticación. |
| RNF-02 | Sincronización completa del catálogo en menos de 2 minutos. |
| RNF-03 | Generación de menú en menos de 10 segundos (p95) para 14 días y 4 personas. |
| RNF-04 | La app sigue operativa con la última copia del catálogo si la API falla, sin mezclar almacenes. |
| RNF-05 | Código tipado, con tests y migraciones de base de datos. |
| RNF-06 | Sin telemetría ni envío de datos personales. |
| RNF-07 | Interfaz responsive para escritorio/tableta; la compra se lleva con lista imprimible/exportable. |
| RNF-08 | Importes calculados con `Decimal`; nunca con `float`. |
| RNF-09 | Respeto de rate limits y caché; sin llamadas en bucle. |
| RNF-10 | Instalación y arranque reproducibles con un comando en Windows. |

---

## 4. Flujo de usuario

### 4.1 Primer arranque

1. La app comprueba si hay catálogo.
2. Si no hay, sincroniza Mercadona y muestra progreso.
3. Si falla, muestra el error y permite reintentar.
4. Si el almacén resuelto no es 4389, no genera menús; muestra un error claro.

### 4.2 Crear menú

Pantalla principal:

- **Personas:** 1-10.
- **Días:** 1-14.
- **Presupuesto total:** euros para todo el periodo.
- **Comidas incluidas:** comida y cena (fijo, 2 al día).
- Enlace opcional a **preferencias**: exclusiones, alérgenos y despensa.

Botón: **Generar menú**.

### 4.3 Revisar menú

- Cabecera: “Menú para 7 días · 2 personas · Presupuesto 70 €”.
- Barra de presupuesto: ticket, consumo, despensa y sobrante.
- Rejilla de días × 2 comidas.
- Cada plato muestra: nombre, ingredientes principales, coste por ración y etiquetas.
- Acciones: **cambiar**, **no me gusta**, **bloquear**.
- Botón **regenerar** respetando bloqueos.
- Botón **lista de la compra**.

### 4.4 Lista de la compra

- Agrupada por secciones de Mercadona.
- Cada línea: producto, cantidad necesaria, paquetes, precio, subtotal.
- Checkbox de comprado.
- Toggle “ya lo tengo” para descontar de despensa.
- Total y aviso de sobras.
- Imprimir/exportar.

### 4.5 Configuración

- Ingredientes, platos y etiquetas excluidos.
- Alérgenos declarados.
- Despensa por ingrediente y cantidad.
- Estado de sincronización y última actualización.
- Aviso legal y de alérgenos.

---

## 5. Modelo de dominio

### 5.1 Producto de Mercadona (`Product`)

Producto real del catálogo online:

- id, EAN, nombre, marca, categoría;
- formato;
- cantidad y unidad normalizadas del paquete;
- precio del paquete;
- precio de referencia para mostrar (€/kg o €/L);
- imagen y disponibilidad;
- fecha de última observación y sync.

### 5.2 Ingrediente (`Ingredient`)

Concepto culinario canónico:

- “pechuga de pollo”, “arroz redondo”, “tomate triturado”, “huevo”.
- Una única unidad base: gramos, mililitros o unidades.
- Grupo: verdura, proteína, hidrato, lácteo, grasa, fruta, despensa, otro.
- Fuente de proteína, cuando aplique.
- Alérgenos canónicos.
- Peso medio por unidad, cuando se compra por pieza.

### 5.3 Plato (`Dish`)

Ficha de un plato, **sin receta**:

- slug estable, nombre y descripción breve opcional;
- raciones base;
- tipos de comida compatibles: `lunch`, `dinner`, `both`;
- fuentes de proteína;
- etiquetas: verdura, hidrato, ligero, etc.;
- composición: ingredientes y cantidades en la unidad base del ingrediente.

La UI muestra el plato y sus productos. **No hay pasos de cocina.**

### 5.4 Menú (`Menu`)

- personas, días, presupuesto;
- CP y almacén;
- estado;
- entradas: día, comida/cena, plato, bloqueado;
- coste de consumo, ticket, despensa y sobras;
- fecha de precios y `sync_run_id`;
- snapshot de preferencias y despensa usado al generar.

### 5.5 Perfil (`Profile`)

- fila única (`id=1`) en el MVP;
- últimos valores usados de personas, días y presupuesto;
- alérgenos declarados;
- exclusiones;
- despensa.

---

## 6. Reglas de negocio

### 6.1 Presupuesto

- El presupuesto es **total para el periodo**.
- Se muestra también el equivalente diario, por persona y por comida.
- Es un **límite máximo duro** para menús válidos.
- Si el mínimo posible supera el presupuesto:
  - se devuelve `status="infeasible"` e `is_preview=true`;
  - `reason="budget"`;
  - `entries` contiene el mejor menú mínimo encontrado, marcado como preview;
  - se incluye `minimum_ticket_cents` y `minimum_is_estimate`;
  - `shortfall_cents = max(0, minimum_ticket_cents − budget_cents)`;
  - `menu_id=null`;
  - no se genera lista de la compra oficial;
  - se ofrecen sugerencias genéricas (subir presupuesto, reducir días/personas, permitir repeticiones, añadir despensa).
- Si la inviabilidad no es de presupuesto (repeticiones, mínimos diarios, bloqueos o falta de asignación), se devuelve `422 NO_FEASIBLE_MENU` con `reason` y sin preview.
- `minimum_ticket_cents` solo se etiqueta como mínimo si el fallback prueba optimalidad; en caso contrario, `minimum_is_estimate=true`.

### 6.2 Coste de consumo y ticket

| Concepto | Definición |
|---|---|
| Necesidad bruta | cantidad de ingrediente que requiere el menú |
| Despensa | cantidad de ingrediente que el usuario ya tiene |
| Necesidad neta | `max(0, necesidad bruta − despensa)` |
| Ticket | suma de paquetes comprados × precio del paquete |
| Consumo | valor de la cantidad usada, incluida la despensa |
| Consumo de despensa | valor de la parte cubierta por despensa |
| Consumo comprado | `consumo − consumo de despensa` |
| Sobras | `ticket − consumo comprado` |

Identidad obligatoria:

```text
ticket + consumo_despensa = consumo + sobras
```

Reglas de valoración:

- La despensa se valora al coste unitario del formato elegible más barato para ese ingrediente; si no hay compra, se usa el producto por defecto.
- `Σ menu_entry_ingredients.consumption_cents = menu_entries.entry_consumption_cents`.
- `Σ menu_entries.entry_consumption_cents = menus.consumption_cents`.
- `Σ shopping_items.subtotal_cents = menus.ticket_cents`.
- Cualquier mutación del menú o revalidación de precios recalcula ticket, lista y costes por entrada en la misma transacción.
- “Ya lo tengo” en la lista modifica el snapshot de despensa del menú y recalcula; si el ticket resultante supera el presupuesto, se rechaza con `BUDGET_EXCEEDED`.

### 6.3 Paquetes, formatos y plan de compra

- Cada producto tiene una cantidad de paquete normalizada a la unidad base del ingrediente.
- La compra se redondea siempre hacia arriba: `ceil(necesidad_neta / cantidad_paquete)`.
- Un ingrediente puede tener varios formatos.
- **Plan canónico `plan_purchase(ingrediente, necesidad_neta)`:** elige la combinación de paquetes que minimiza `Σ q[p] × precio[p]` sujeto a `Σ q[p] × cantidad_paquete[p] ≥ necesidad_neta`. Permite mezclar formatos. Desempate: menos paquetes, menor precio total y `product_id` estable.
- F3 usa `plan_purchase` para el preview. F4 usa variables `q` para imponer el presupuesto, y la lista final se materializa con `plan_purchase` sobre la necesidad agregada. Como el plan canónico es óptimo para el mismo ingrediente, su ticket es ≤ al del solver y ≤ presupuesto.
- El consumo se asigna a los formatos comprados de menor precio unitario primero.
- La lista de la compra se deriva del plan canónico; no se recalcula con otro criterio.
- Las sobras se valoran a precio de compra y se muestran; no se arrastran entre menús en el MVP.

### 6.4 Despensa

- Por ingrediente y cantidad en unidad base. La unidad se toma de `ingredients.base_unit`; no se duplica en la despensa.
- `net_need = max(0, need − pantry)` antes de calcular paquetes.
- La UI ofrece “tengo suficiente” como atajo que fija la cantidad del snapshot a la necesidad actual.
- “Tengo suficiente” no modifica la despensa global; solo el snapshot del menú. La despensa global se edita en ajustes.
- La despensa no se descuenta del consumo; se contabiliza aparte.
- El arrastre de despensa entre menús queda en el backlog.

### 6.5 Alérgenos y exclusiones

Lista canónica: `gluten`, `crustaceans`, `eggs`, `fish`, `peanuts`, `soybeans`, `milk`, `nuts`, `celery`, `mustard`, `sesame`, `sulphites`, `lupin`, `molluscs` y `unknown`.

- Cada producto tiene `allergen_status ∈ {known, partial, unknown}`.
- `product_allergens` guarda los alérgenos conocidos; la ausencia de filas solo es “sin alérgenos” si `allergen_status=known`.
- `P_i` (productos elegibles de un ingrediente) solo incluye productos con `allergen_status=known` y sin ningún alérgeno declarado por el usuario.
- Si `allergen_status=partial` o `unknown` y el usuario declara al menos un alérgeno, el producto no es elegible.
- La unión de alérgenos de ingrediente y producto es la fuente de verdad; un producto no puede eliminar un alérgeno declarado por el ingrediente.
- Si `P_i` queda vacío, el ingrediente es inelegible y se excluyen sus platos.
- “Producto de respaldo” es el siguiente producto elegible por prioridad después del filtrado; nunca uno con alérgeno desconocido si el usuario declaró alérgenos.
- Los alérgenos no se pueden eliminar desde “no me gusta”; son un campo separado y estricto.
- Exclusiones:
  - por ingrediente: elimina platos que lo contienen;
  - por plato: elimina ese plato;
  - por etiqueta: elimina grupos (“pescado”, “picante”, “cuchara”).
- Las exclusiones y los alérgenos se aplican antes de optimizar y **nunca se relajan**.
- Aviso legal: la app no sustituye el etiquetado oficial.

### 6.6 Equilibrio y variedad

Mínimos diarios duros, **por persona y día**, calculados desde la composición:

- 1 ración de verdura = 150 g.
- 1 ración de proteína = 100 g de carne/pescado, 2 huevos, 80 g de legumbre seca o 200 ml de lácteo.
- 1 ración de hidrato = 60 g de arroz/pasta en seco, 150 g de patata o 60 g de pan.

Cada ingrediente declara `serving_group` (`vegetable`, `protein`, `carb`, `none`) y `serving_size_milli`. La composición del plato calcula las raciones. Los mínimos son 1 ración de verdura, 1 de proteína y 1 de hidrato por persona y día.

Variedad, modelada como violaciones minimizadas:

| Regla | Métrica | Umbral | Violación |
|---|---|---|---|
| Variedad de proteína | fuentes distintas | `min(3, days)` | `max(0, umbral − distintas)` |
| Pescado | platos con pescado | `ceil(days / 7)` | `max(0, umbral − platos)` |
| Legumbres | platos con legumbre | `ceil(days / 7)` | `max(0, umbral − platos)` |
| Carne roja | platos con carne roja | `ceil(days × 3 / 7)` | `max(0, platos − umbral)` |
| Cenas ligeras | cenas `light` | `ceil(days / 2)` | `max(0, umbral − cenas)` |
| Variedad de hidratos | fuentes distintas | `min(2, days)` | `max(0, umbral − distintas)` |

Todas las violaciones tienen peso 1. La etapa 1 minimiza la suma de violaciones; la etapa 2 minimiza el ticket con esa suma fijada.

`light` se define por composición: sin carne roja, al menos 1 ración de verdura y como máximo 1 ración de hidrato. No depende de si el plato se fríe, porque no hay pasos de cocina.

`has_vegetables`, `light`, `carbs` y `protein_sources` se derivan de la composición al cargar el seed y se guardan como caché validada. El YAML puede declararlos, pero `validate_seed` debe comprobar que coinciden con la composición.

Para menús de 1-2 días se aplican los mínimos diarios y los umbrales de variedad con `min`/`ceil`; no se relajan los mínimos diarios.

---

## 7. Stack tecnológico

| Capa | Tecnología | Motivo |
|---|---|---|
| Lenguaje backend | Python 3.13 | Ecosistema de optimización y datos |
| API | FastAPI + Uvicorn | Tipado, rápido, OpenAPI automático |
| Validación | Pydantic v2 | Esquemas claros y configuración |
| ORM | SQLAlchemy 2 | Modelo explícito y migraciones |
| Migraciones | Alembic | Evolución controlada del esquema |
| Base de datos | SQLite (WAL) en `%LOCALAPPDATA%\Cesta` | Local, fuera de OneDrive, suficiente |
| Cliente HTTP | httpx + tenacity | Async, reintentos y timeouts |
| Optimización | OR-Tools CP-SAT | Modelo entero con paquetes y presupuesto |
| Frontend | React 19 + Vite + TypeScript | Interfaz interactiva para el menú |
| Estilos | Tailwind CSS 4 + shadcn/ui | UI consistente y accesible |
| Estado servidor | TanStack Query | Caché, mutaciones y estados |
| Rutas | React Router | Navegación SPA |
| Formularios | React Hook Form + Zod | Validación tipada |
| Iconos | Lucide | Iconografía ligera |
| Tests backend | pytest + respx | Unitarios e integración sin red |
| Tests frontend | Vitest + Testing Library + MSW | Componentes y flujos |
| Tooling Python | uv, Ruff, mypy | Reproducibilidad y calidad |
| Tooling frontend | npm, ESLint, Prettier | Estándar del ecosistema |
| Arranque local | `run.ps1` | Un comando en Windows |

### 7.1 Decisiones de stack

- **No Streamlit.** La interfaz necesita edición de menús, bloqueos, cambios y lista de la compra.
- **No Postgres/Redis/Celery.** Un usuario local y ~4.000 productos no lo justifican.
- **No Docker en el MVP.** No está instalado; se añadirá como opción de despliegue.
- **No Next.js.** FastAPI cubre el backend y el optimizador está en Python.
- **No APScheduler.** Basta con sync al arrancar + botón manual + tarea asyncio con lock.
- **No Recharts.** La barra de presupuesto se hace con CSS.
- **No Playwright en el MVP.** Queda como mejora.
- **No `price_snapshots` en el MVP.** Precio actual + snapshot de menú; historial en backlog.
- **No `raw_json` persistente.** Fixtures mínimas y sintéticas para tests.
- **No API de terceros de pago.** Se usa la API pública de Mercadona.

---

## 8. Arquitectura

```text
┌──────────────────────────────┐
│  Navegador (React + Vite)    │
│  Menú · Lista · Ajustes      │
└──────────────┬───────────────┘
               │ HTTP /api
┌──────────────▼───────────────┐
│  FastAPI                     │
│  ├─ Catalog API              │
│  ├─ Dishes API               │
│  ├─ Menu API                 │
│  ├─ Preferences API          │
│  └─ Services                 │
│      ├─ MercadonaClient      │
│      ├─ CatalogSync          │
│      ├─ Pricing              │
│      ├─ Optimizer (CP-SAT)   │
│      └─ MenuService          │
└──────────────┬───────────────┘
               │ SQLAlchemy
┌──────────────▼───────────────┐
│  SQLite                      │
│  %LOCALAPPDATA%\Cesta\       │
│  cesta.db                    │
└──────────────▲───────────────┘
               │ sync (solo lectura)
┌──────────────┴───────────────┐
│ tienda.mercadona.es/api      │
│ CP 22002 · almacén 4389      │
└──────────────────────────────┘
```

### 8.1 Componentes

- **MercadonaClient:** fija el CP 22002, obtiene el almacén, descarga categorías y productos, normaliza respuestas.
- **CatalogSyncService:** sincroniza por subcategoría, registra éxito/fallo parcial, marca disponibilidad solo en categorías correctas.
- **PricingService:** normaliza unidades, calcula necesidad neta, paquetes, consumo, ticket, despensa y sobras.
- **OptimizerService:** construye y resuelve el modelo CP-SAT en dos etapas.
- **MenuService:** persiste menús, aplica bloqueos/cambios, regenera, recalcula lista y valida presupuesto.
- **SeedService:** carga ingredientes, productos asociados y platos desde YAML de forma idempotente.

### 8.2 Flujo de datos

1. Sync descarga productos y precios.
2. El seed de platos se carga y valida contra productos disponibles.
3. El usuario configura personas, días, presupuesto, exclusiones, alérgenos y despensa.
4. El optimizador filtra platos elegibles y resuelve.
5. MenuService guarda el menú y materializa la lista de la compra.
6. Cualquier cambio posterior recalcula ticket y lista en la misma transacción.

---

## 9. Modelo de datos

### 9.1 Catálogo

```text
categories
  id, name, parent_id, level, is_food, sort_order

products
  id, external_id UNIQUE, ean, name, brand, category_id, packaging,
  package_quantity_milli, package_unit, is_estimated,
  package_price_cents, reference_price_cents, reference_unit,
  is_pack, approx_size, selling_method, allergen_status,
  thumbnail_url, published, unavailable_from,
  first_seen_at, last_seen_at, last_sync_run_id

sync_runs
  id, started_at, finished_at, status,
  postal_code, warehouse,
  categories_ok, categories_failed, products_seen, error

sync_category_runs
  id, sync_run_id, category_id, status, products_seen, error

product_allergens
  product_id, allergen_code, source, confidence,
  PRIMARY KEY (product_id, allergen_code)
```

### 9.2 Ingredientes y platos

```text
ingredients
  id, slug, name, category, group, base_unit,
  grams_per_unit, protein_source,
  serving_group, serving_size_milli,
  allergens_json, tags_json, active

ingredient_products
  id, ingredient_id, product_id,
  is_default, priority, notes,
  UNIQUE(product_id)           -- un producto = un ingrediente

dishes
  id, slug, name, description, base_servings,
  meal_types_json, protein_sources_json,
  has_vegetables, light, carbs, tags_json,
  active, seed_version

dish_ingredients
  id, dish_id, ingredient_id,
  quantity_milli           -- en la unidad base del ingrediente
```

### 9.3 Usuario y menús

```text
profiles
  id=1, people, days, budget_cents,
  allergen_codes_json, created_at, updated_at

exclusions
  id, profile_id,
  ingredient_id NULL, dish_id NULL, tag NULL,
  created_at,
  CHECK ((ingredient_id IS NOT NULL) + (dish_id IS NOT NULL) + (tag IS NOT NULL) = 1)
  -- índices únicos parciales:
  -- UNIQUE(profile_id, ingredient_id) WHERE ingredient_id IS NOT NULL
  -- UNIQUE(profile_id, dish_id) WHERE dish_id IS NOT NULL
  -- UNIQUE(profile_id, tag) WHERE tag IS NOT NULL

pantry_items
  id, profile_id, ingredient_id,
  quantity_milli, updated_at,
  UNIQUE(profile_id, ingredient_id)

menus
  id, profile_id, people, days, budget_cents, status,
  price_status, timed_out, revalidated_ticket_cents,
  ticket_cents, consumption_cents, pantry_consumption_cents,
  leftover_value_cents,
  postal_code, warehouse, prices_captured_at, sync_run_id,
  optimizer_version, settings_json,
  created_at, updated_at

-- status persistido: optimal | feasible | relaxed
-- price_status: current | stale
-- settings_json: MenuSettings validado
--   (exclusiones, despensa, alérgenos, max_repeats, optimizer_version)

menu_entries
  id, menu_id, day_index, slot, dish_id, dish_name,
  locked, entry_consumption_cents, entry_protein_source,
  UNIQUE(menu_id, day_index, slot)

menu_entry_ingredients
  id, entry_id, ingredient_id, product_id,
  used_milli, consumption_cents

shopping_items
  id, menu_id, product_id, ingredient_id,
  packages, package_quantity_milli, package_price_cents,
  subtotal_cents, pantry_quantity_milli, checked,
  UNIQUE(menu_id, product_id)
```

### 9.4 Restricciones

- `PRAGMA foreign_keys = ON` en cada conexión.
- `PRAGMA busy_timeout = 5000`.
- `external_id` de producto es la clave natural de upsert; EAN es informativo.
- `UNIQUE(menu_id, product_id)` en `shopping_items`.
- `UNIQUE(product_id)` en `ingredient_products`.
- `UNIQUE(menu_id, day_index, slot)`.
- Índices únicos parciales para exclusiones (SQLite trata NULL como distinto).
- Sin `position` redundante.
- Sin `optional` en ingredientes de plato en el MVP.
- `settings_json` validado con un esquema Pydantic versionado.

---

## 10. API

Prefijo `/api`. Errores homogéneos:

```json
{
  "error": {
    "code": "CODE",
    "message": "Mensaje para el usuario",
    "details": {}
  }
}
```

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/health` | Estado del servicio |
| GET | `/api/catalog/status` | Última sync, progreso, errores |
| POST | `/api/catalog/sync` | Fuerza sincronización |
| GET | `/api/catalog/categories` | Árbol de categorías |
| GET | `/api/catalog/products` | Búsqueda y listado paginado |
| GET | `/api/catalog/products/{id}` | Detalle de producto |
| GET | `/api/allergens` | Lista canónica de alérgenos |
| GET | `/api/ingredients` | Ingredientes activos con búsqueda y grupo |
| GET | `/api/dishes` | Catálogo de platos |
| GET | `/api/dishes/{id}` | Detalle, composición y alérgenos |
| GET | `/api/profile` | Perfil y preferencias |
| PUT | `/api/profile` | Actualiza perfil |
| GET | `/api/exclusions` | Exclusiones |
| POST | `/api/exclusions` | Crea exclusión |
| DELETE | `/api/exclusions/{id}` | Elimina exclusión |
| GET | `/api/pantry` | Despensa |
| PUT | `/api/pantry` | Actualiza despensa |
| POST | `/api/pricing/preview` | Previsualiza coste sin persistir menú |
| POST | `/api/menus/generate` | Genera menú |
| GET | `/api/menus` | Historial paginado |
| GET | `/api/menus/{id}` | Menú completo |
| PATCH | `/api/menus/{id}/entries/{entry_id}` | Bloquea/desbloquea un plato |
| POST | `/api/menus/{id}/entries/{entry_id}/swap` | Busca alternativa |
| POST | `/api/menus/{id}/entries/{entry_id}/exclude` | Excluye plato del menú o del perfil |
| POST | `/api/menus/{id}/regenerate` | Regenera respetando bloqueos |
| POST | `/api/menus/{id}/revalidate` | Recalcula precios, ticket y lista actuales |
| GET | `/api/menus/{id}/shopping-list` | Lista de la compra |
| PATCH | `/api/menus/{id}/shopping-list/items/{item_id}` | Marca comprado |
| GET | `/api/menus/{id}/export` | Exporta markdown/CSV |

### 10.1 Generación

```json
{
  "people": 2,
  "days": 7,
  "budget_cents": 7000,
  "allergen_codes": [],
  "excluded_ingredient_ids": [],
  "excluded_dish_ids": [],
  "excluded_tags": [],
  "pantry": [
    {"ingredient_id": 12, "quantity_milli": 500000, "unit": "g"}
  ],
  "max_repeats": 1
}
```

### 10.2 Respuesta de generación

```json
{
  "status": "optimal",
  "is_preview": false,
  "reason": null,
  "menu_id": 123,
  "people": 2,
  "days": 7,
  "budget_cents": 7000,
  "ticket_cents": 6840,
  "consumption_cents": 6120,
  "pantry_consumption_cents": 0,
  "leftover_value_cents": 720,
  "minimum_ticket_cents": null,
  "minimum_is_estimate": false,
  "shortfall_cents": 0,
  "relaxations": [],
  "suggestions": [],
  "price_status": "current",
  "timed_out": false,
  "postal_code": "22002",
  "warehouse": "4389",
  "prices_captured_at": "2026-10-25T18:00:00Z",
  "entries": []
}
```

### 10.3 Estados

- **Generación:** `optimal`, `feasible`, `relaxed`, `infeasible`, `timeout`.
- **Persistido:** `optimal`, `feasible`, `relaxed`; `timed_out=true` si se guardó el mejor esfuerzo.
- **Precio:** `price_status ∈ {current, stale}`. `stale` no sustituye al estado de generación.
- `optimal`: solución óptima probada.
- `feasible`: solución válida sin prueba de optimalidad (incluye timeout con mejor esfuerzo persistido).
- `relaxed`: se relajaron reglas de variedad; se listan.
- `infeasible`: el mínimo supera el presupuesto; `menu_id=null`, `is_preview=true`, `reason="budget"`.
- `no_eligible_dishes`: no hay platos elegibles; **solo 422**, no estado de menú.
- `timeout`: sin solución dentro del tiempo y sin mejor esfuerzo; `menu_id=null`.
- `stale`: `price_status` de un menú guardado con precios cambiados; se recalcula al abrir o con `/revalidate`.

### 10.4 Códigos de error

| Código | HTTP | Uso |
|---|---|---|
| `CATALOG_EMPTY` | 503 | No hay catálogo sincronizado |
| `SYNC_IN_PROGRESS` | 409 | Ya hay una sync en curso |
| `WAREHOUSE_UNAVAILABLE` | 503 | No se pudo confirmar 4389 |
| `NO_ELIGIBLE_DISHES` | 422 | Exclusiones/alérgenos dejan el catálogo vacío |
| `NO_FEASIBLE_MENU` | 422 | Inviabilidad por repeticiones, mínimos, bloqueos o asignación |
| `BUDGET_EXCEEDED` | 422 | Un cambio manual o “ya lo tengo” supera el presupuesto |
| `INVALID_EXCLUSION` | 422 | Referencia o etiqueta inválida |
| `PRODUCT_UNAVAILABLE` | 409 | Producto necesario no disponible |
| `SOLVER_TIMEOUT` | 200 | Estado `timeout`; si hay mejor esfuerzo se persiste como `feasible` con `timed_out=true` |
| `NOT_FOUND` | 404 | Menú, entrada, producto o plato inexistente |
| `INVALID_HOST` | 400 | Cabecera `Host` fuera de la allowlist local |
| `VALIDATION_ERROR` | 422 | Entrada inválida, sobre homogéneo |

---

## 11. Optimizador

### 11.1 Unidades enteras y coeficientes

- Todas las cantidades se guardan en **milésimas de unidad base**: mg, µl o mili-unidades.
- `1 g = 1000`, `1 ml = 1000`, `1 unidad = 1000`.
- Coeficiente de un plato para un ingrediente:

```text
coef[r,i] = round(quantity_milli[r,i] × people / base_servings[r])
need_i(x) = Σ_{r,d,s} coef[r,i] × x[r,d,s]
```

- El redondeo se aplica **por plato** antes de multiplicar por `x`, no al total.
- Los coeficientes de CP-SAT son enteros; los costes, céntimos enteros.
- Las cantidades fraccionarias de piezas se permiten en el cálculo; la UI las redondea y la compra usa paquetes completos.

### 11.2 Variables

- `x[r,d,s] ∈ {0,1}`: plato `r` en día `d`, hueco `s`.
- `q[p] ∈ Z+`: paquetes comprados del producto `p`.
- `violation[k] ∈ Z+`: incumplimiento de la regla de variedad `k`.

`used[p]` y `leftover[p]` no son variables del solver: se calculan después de resolver con el plan canónico de §11.7.

### 11.3 Restricciones duras

1. `Σ_r x[r,d,s] = 1` para cada día y hueco.
2. `x[r,d,s] = 0` si el plato no es compatible con el hueco, está excluido o contiene un alérgeno.
3. `Σ_{d,s} x[r,d,s] ≤ max_repeats` (por defecto 1).
4. Entradas bloqueadas: `x[r,d,s] = 1`.
5. Demanda dependiente de la selección:

```text
Σ_{p∈P_i} q[p] × package_quantity_milli[p] + pantry_milli[i] ≥ need_i(x)
```

6. Presupuesto:

```text
Σ_p q[p] × package_price_cents[p] ≤ budget_cents
```

7. Mínimos diarios por persona: 1 ración de verdura, 1 de proteína y 1 de hidrato, calculados desde `serving_group`/`serving_size_milli`.
8. `UNIQUE(product_id)` garantiza que un producto no se cuenta en dos ingredientes.
9. Los platos deben ser compatibles con el hueco (`lunch`/`dinner`/`both`).
10. Un plato no puede aparecer dos veces en el mismo día.

### 11.4 Objetivo lexicográfico

Las reglas de variedad se definen en §6.6 con métricas, umbrales y violaciones. Todas las violaciones tienen peso 1.

**Etapa 1:** minimizar la suma de violaciones.

```text
min Σ_k violation[k]
```

Sujeto a todas las restricciones duras, incluido el presupuesto.

**Etapa 2:** fijar la suma óptima de violaciones de la etapa 1 y minimizar el ticket.

```text
min Σ_p q[p] × package_price_cents[p]
```

Así se obtiene el **menú más barato que cumple la variedad** cuando las violaciones son 0. Si no es posible cumplir toda la variedad, se obtiene el menú más barato con el mínimo de violaciones, y se informa.

Si la etapa 1 termina por tiempo sin prueba de optimalidad, se usa el mejor incumbente, se ejecuta la etapa 2 como mejora y se devuelve `status="feasible"`, nunca `optimal`.

### 11.5 Inviabilidad

Causas posibles: `budget`, `repeats`, `minimums`, `locks`, `no_assignment`.

- **Budget:** se resuelve un modelo sin presupuesto para obtener el mejor ticket posible. Si se prueba optimalidad, `minimum_ticket_cents` es el mínimo; si no, `minimum_is_estimate=true`. Se devuelve `status="infeasible"`, `is_preview=true`, `reason="budget"`, preview y `shortfall_cents`.
- **Repeats/minimums/locks/no_assignment:** se devuelve `422 NO_FEASIBLE_MENU` con `reason` y sugerencias; no se inventa un menú.
- No se persiste ningún preview.
- No se relajan alérgenos, dieta, exclusiones ni presupuesto para presentar un menú válido.
- Las repeticiones no se relajan automáticamente; se sugiere subir `max_repeats`.
- Si `regenerate` con bloqueos es inviable, `reason="locks"`.

### 11.6 Tiempo y determinismo

- Presupuesto total del solver: **8 s**.
- Etapa 1: 3 s. Etapa 2: 3 s. Fallback de mínimo: 2 s.
- La generación p95 debe ser < 10 s incluyendo API y serialización.
- `num_search_workers=1` y semilla fija para tests y reproducibilidad.
- Si se agota el tiempo:
  - con mejor esfuerzo, se persiste `feasible` con `timed_out=true`;
  - sin mejor esfuerzo, se devuelve `timeout` con `menu_id=null`.

### 11.7 Post-cálculo determinista

Tras resolver:

1. Agregar `need_i` por ingrediente.
2. Aplicar `plan_purchase` de §6.3 para obtener `q_canónico[p]`.
3. Verificar `ticket_canónico ≤ ticket_solver ≤ budget_cents`; si no, error interno.
4. Asignar `used[p]` a los formatos comprados de menor precio unitario primero.
5. `leftover[p] = q_canónico[p] × package_quantity_milli[p] − used[p]`.
6. Calcular `consumption_cents`, `pantry_consumption_cents` y `leftover_value_cents`.
7. Repartir `entry_consumption_cents` proporcionalmente a `used_milli` y verificar las sumas de §6.2.
8. Materializar `shopping_items` desde `q_canónico`.

El preview de F3 y la lista de F4 usan la misma función `plan_purchase`; para un mismo menú, `preview.ticket == shopping_list.ticket`.

---

## 12. Integración con Mercadona

### 12.1 Fuente

- Base: `https://tienda.mercadona.es/api`.
- Sin autenticación.
- API no oficial, la misma que usa la tienda online.
- Uso personal; no redistribuir el catálogo.

### 12.2 Código postal y almacén

- CP fijo del MVP: **22002 (Huesca)**.
- Almacén esperado: **4389**.
- Fijación:

```http
PUT /api/postal-codes/actions/change-pc/
Content-Type: application/json

{"new_postal_code":"22002"}
```

Respuesta observada:

```text
x-customer-pc: 22002
x-customer-wh: 4389
```

- Las peticiones de catálogo usan `?wh=4389` y mantienen la sesión/cookies.
- Si no se confirma `x-customer-wh=4389`, no se genera menú.
- La copia local solo se usa si su `warehouse` registrado es `4389` y su `postal_code` es `22002`. En ese caso sirve para consultar menús guardados y precios, **no para generar menús nuevos** mientras la API no confirme el almacén.
- Si la copia local es de otro almacén, no se usa para generar ni para mostrar precios actuales.
- Cambiar el CP queda en el backlog.

### 12.3 Descarga

1. `GET /api/categories/` → 26 secciones.
2. Cada sección contiene sus subcategorías (152 en total).
3. `GET /api/categories/{subcategory_id}/?wh=4389` → productos.
4. `GET /api/products/{id}/` solo para productos usados en platos (alérgenos y detalle).

Datos observados:

- ~4.327 productos únicos.
- ~152 subcategorías.
- Sincronización secuencial ~65 s; con concurrencia 4, menos de 30 s.
- Precios y disponibilidad pueden variar por almacén y fecha.
- Los conteos son observaciones, no garantías; el DoD usa umbrales.

### 12.4 Normalización

- Parsear importes con coma o punto y espacios.
- Usar `Decimal`; guardar céntimos en la base de datos.
- Normalizar `unit_size` y `size_format` a milésimas de g/ml/unidad.
- Respetar `is_pack`, `pack_size`, `approx_size` y `selling_method`.
- Evitar productos de mostrador o peso variable en el MVP.
- Guardar precio de paquete, cantidad de paquete y unidad; no guardar un “precio por gramo” en céntimos.
- Si un producto tiene formato no reconocible, excluirlo del mapeo y registrar advertencia.

### 12.5 Sync y fallos parciales

- Concurrencia máxima 4; reintentos con backoff.
- Registrar éxito/fallo por subcategoría.
- Marcar no disponible solo productos de subcategorías descargadas correctamente.
- `sync_runs.status`: `success`, `partial`, `failed`.
- Si una sync es parcial, no marcar como no disponibles los productos de categorías fallidas.
- No solapar syncs; usar lock.

### 12.6 Rate limiting y caché

- Sincronización diaria o manual; no por cada visita.
- Última copia local como fallback.
- No guardar respuestas completas del catálogo en el repositorio.

### 12.7 Aviso legal

- La app no está afiliada a Mercadona.
- Precios de la tienda online, no de tienda física.
- Pueden cambiar sin aviso.
- No se automatiza la compra.
- Los alérgenos deben confirmarse en el etiquetado del producto.

---

## 13. Catálogo de platos e ingredientes

### 13.1 Estrategia

- **50-60 platos** iniciales, españoles/mediterráneos.
- **~120 ingredientes** canónicos.
- Cada ingrediente mapeado a 1-3 productos, con formato y cantidad de paquete.
- Cada plato tiene 4-8 ingredientes, raciones base y etiquetas.
- Sin pasos de cocina.
- Slugs y enums en inglés; nombres y UI en español.

### 13.2 Cobertura mínima

Para que 14 días × 2 comidas sean viables:

- ≥ 14 platos compatibles con `lunch`;
- ≥ 14 platos compatibles con `dinner`;
- ≥ 28 platos elegibles con exclusiones por defecto;
- ≥ 3 fuentes de proteína con ≥ 4 platos cada una;
- ≥ 2 platos de pescado, ≥ 2 de legumbre, ≥ 2 de carne roja;
- ≥ 4 cenas ligeras;
- ≥ 1 verdura y ≥ 1 hidrato disponibles cada día.

`validate_seed` comprueba estos umbrales y la elegibilidad con exclusiones por defecto. El dry-run del optimizador se ejecuta en F4.9, cuando el modelo ya existe.

### 13.3 Formato YAML

```yaml
- slug: chicken-rice-vegetables
  name: Pollo con arroz y verduras
  description: Plato completo de pollo, arroz y pimiento.
  base_servings: 2
  meal_types: [lunch, dinner]
  protein_sources: [chicken]
  has_vegetables: true
  light: false
  carbs: rice
  tags: [balanced]
  ingredients:
    - ingredient: chicken-breast
      quantity: 300
      unit: g
    - ingredient: rice
      quantity: 160
      unit: g
    - ingredient: red-pepper
      quantity: 1
      unit: unit
    - ingredient: olive-oil
      quantity: 15
      unit: ml
```

### 13.4 Validación

Script obligatorio antes de generar menús:

- todos los ingredientes del plato existen;
- todos los ingredientes tienen al menos un producto disponible;
- cada producto pertenece a un solo ingrediente;
- las unidades son coherentes con la unidad base;
- los productos tienen precio y cantidad de paquete;
- las cantidades son positivas;
- los alérgenos están etiquetados o marcados `unknown`;
- se cumplen los umbrales de cobertura;
- no hay platos sin proteína o sin verdura cuando corresponda;
- la elegibilidad con exclusiones por defecto deja al menos `días × 2` platos para 14 días.

El dry-run del optimizador para los escenarios de 1, 2, 7 y 14 días se ejecuta en F4.9, cuando el modelo ya existe.

Si falla, la app muestra un error claro y no genera el menú.

---

## 14. Frontend y UX

### 14.1 Páginas

| Ruta | Pantalla |
|---|---|
| `/` | Crear menú: personas, días, presupuesto |
| `/menus/:id` | Menú generado |
| `/menus/:id/shopping-list` | Lista de la compra |
| `/dishes` | Catálogo de platos (sin pasos) |
| `/history` | Menús guardados |
| `/settings` | Exclusiones, alérgenos, despensa, sync |

### 14.2 Componentes clave

- Formulario de presupuesto con equivalencia €/día, €/persona/día y €/comida.
- Tarjeta de plato con coste, etiquetas y acciones.
- Barra de presupuesto con ticket, consumo, despensa y sobrante.
- Modal de menú inviable con mínimo, déficit y sugerencias.
- Lista de la compra agrupada y con checkboxes.
- Estado de sincronización con progreso.
- Banner de precios desactualizados y delta.
- Aviso de alérgenos y etiquetado.

### 14.3 Estados

- Cargando catálogo.
- Catálogo vacío o incompleto.
- Generando menú.
- Menú óptimo.
- Menú con relajaciones.
- Menú inviable.
- Sin platos elegibles.
- Error de red.
- Menú `stale` por cambio de precios.

### 14.4 Accesibilidad y alcance

- Contraste suficiente.
- Navegación por teclado.
- Etiquetas ARIA en formularios y acciones.
- Tamaño táctil adecuado en tableta.
- Textos en español.
- La compra se lleva con la lista imprimible/exportable; el acceso directo desde el móvil por LAN queda en backlog.

---

## 15. Calidad y pruebas

### 15.1 Backend

- Normalización de precios, paquetes y unidades.
- Coste de plato y lista de la compra.
- Identidad contable:
  `ticket + pantry_consumption = consumption + leftover`.
- Optimizador: presupuesto, exclusiones, alérgenos, repeticiones, bloqueos, días.
- Optimalidad con fuerza bruta en una instancia pequeña.
- Validación del seed y cobertura.
- Sync idempotente y fallo parcial.
- Alérgenos: 14 códigos, `unknown`, producto de respaldo, presión de presupuesto.
- Despensa parcial, completa y sobre-despensa.
- Cambio/swap que intenta superar presupuesto.
- Deriva de precios en menús guardados.
- Inyección de fórmulas en CSV.

### 15.2 Casos dorados

- Aceite 5 L vs 1 L.
- Huevos por unidades.
- Pollo 500 g.
- Pack 6 × 125 g.
- 1 persona vs 4 personas.
- 1, 2, 7 y 14 días.
- 1, 2, 4 y 10 personas.
- Despensa con aceite y despensa parcial.
- Presupuesto exacto e imposible.
- Exclusión de pescado.
- Alérgeno `unknown`.
- Producto compartido entre ingredientes (debe fallar la validación).
- Swap que supera presupuesto.
- Precio que sube tras generar.

### 15.3 Frontend

- Tests de formulario y validación.
- Test de rejilla de menú y acciones.
- Test de lista de la compra.
- Tests de estados vacío, inviable y `stale`.
- Build de producción.

### 15.4 Trazabilidad

Cada RF Must debe tener:

- tarea en `TASKS.md`;
- test o validación;
- criterio de aceptación en §19.

La matriz resumida está en §19.3.

---

## 16. Operación local

### 16.1 Comandos previstos

```powershell
# Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev

# Todo
.\run.ps1
```

Si PowerShell bloquea el script:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

### 16.2 Variables de entorno

```env
APP_ENV=local
# CESTA_DATA_DIR=C:\Users\<usuario>\AppData\Local\Cesta
SYNC_ON_STARTUP=true
OPTIMIZER_TIME_LIMIT_SECONDS=8
```

- La base de datos vive por defecto en `%LOCALAPPDATA%\Cesta\cesta.db`, fuera de OneDrive.
- `CESTA_DATA_DIR` es opcional y, si se define, debe ser una ruta absoluta. El valor por defecto se calcula en `config.py` desde `os.environ["LOCALAPPDATA"]`; no se usa `%LOCALAPPDATA%` literal en `.env`.
- El CP es una constante del MVP: `22002`. No se configura por entorno.
- No se configura el almacén por entorno: se deriva del CP y se valida que sea 4389.

### 16.3 Base de datos

- SQLite con WAL.
- `PRAGMA foreign_keys=ON`.
- `PRAGMA busy_timeout=5000`.
- Backup: script que copia la base con la app parada.
- No versionar `cesta.db`, `-wal` ni `-shm`.

### 16.4 Producción local

```powershell
cd frontend
npm run build
cd ..
.\run.ps1 -Prod
```

FastAPI sirve `frontend/dist` y la API en el mismo puerto.

---

## 17. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| La API de Mercadona cambia o bloquea | Alto | Cliente aislado, fixtures sintéticas, snapshot local, modo offline |
| El almacén 4389 no se confirma | Alto | No generar menú; usar última copia marcada sin mezclar almacenes |
| Mapeo ingrediente→producto incorrecto | Alto | `UNIQUE(product_id)`, validador, revisión manual, alternativas |
| Paquetes grandes inflan el ticket para 1 persona | Alto | Doble métrica, despensa básica, sobras, sugerencias |
| Presupuesto imposible | Medio | Preview de mínimo, déficit, sugerencias; no guardar menú inválido |
| Precios cambian tras generar | Medio | Snapshot de precios en el menú; revalidar al abrir y marcar `stale` |
| OR-Tools falla en Windows/Python 3.13 | Alto | Spike F0.6; si falla, cambiar de solver antes de F3/F4 |
| Alérgenos incompletos | Alto | Lista canónica, `unknown` fail-closed, tests, aviso legal |
| OneDrive corrompe SQLite | Medio | BD en `%LOCALAPPDATA%`, WAL, backup |
| CORS/DNS rebinding en local | Medio | Sin CORS en producción, allowlist dev, validar Host |
| Inyección de fórmulas en CSV | Bajo | Escapar celdas que empiezan por `= + - @` |
| Scope creep | Medio | Fases cerradas en TASKS; backlog separado |
| Fechas/estimaciones optimistas | Medio | Reestimar tras F0; registrar real vs estimado |

---

## 18. Fases

El detalle accionable está en `TASKS.md`.

| Fase | Objetivo | Resultado |
|---|---|---|
| F0 | Fundaciones y spikes | Backend, frontend, cliente Mercadona, OR-Tools validado |
| F1 | Catálogo y sync | 4.000+ productos, sync parcial robusta |
| F2 | Ingredientes, platos y preferencias | Seed validado, alérgenos, despensa |
| F3 | Coste puro y preview | Identidad contable y coste verificables |
| F4 | Optimizador y menú | Menú `días × 2` bajo presupuesto |
| F5 | Calidad y entrega | Tests, seguridad, historial, documentación |

---

## 19. Criterios de aceptación

### 19.1 Funcionales

1. En una instalación limpia, `.\run.ps1` arranca la app en local.
2. La pantalla inicial pide personas (1-10), días (1-14) y presupuesto.
3. El catálogo se sincroniza y muestra ≥ 3.000 productos con precios de 22002.
4. El menú contiene exactamente `días × 2` comidas.
5. Ningún plato excluido, ingrediente excluido o alérgeno aparece.
6. Todo menú guardado tiene ticket ≤ presupuesto.
7. Si el mínimo no cabe, se muestra un preview marcado, con mínimo, déficit y sugerencias, y no se guarda.
8. La lista de la compra suma exactamente el ticket.
9. La identidad `ticket + despensa = consumo + sobras` se cumple.
10. La despensa parcial reduce la necesidad antes de calcular paquetes.
11. Se puede cambiar un plato, bloquearlo y regenerar el resto.
12. Un cambio que supera el presupuesto se rechaza con `BUDGET_EXCEEDED`.
13. Se muestran fecha de precios, CP y almacén.
14. Se muestran coste por comida, día y persona.
15. El menú cumple mínimos diarios de verdura, proteína e hidrato.
16. Se muestran alérgenos y aviso legal.
17. El historial guarda nombre y coste del plato aunque el catálogo cambie.
18. La lista se imprime o exporta.
19. La app sigue operativa con la última copia si falla la API.
20. Los tests de coste, identidad, optimizador y alérgenos pasan.

### 19.2 Rendimiento

- Sync completa < 2 min.
- Generación p95 < 10 s para 14 días y 4 personas, medida en el equipo de desarrollo con 20 ejecuciones; el solver tiene 8 s.
- `/api/dishes` < 200 ms con 60 platos.
- UI usable en 1280 px y 768 px; lista imprimible en A4.

### 19.3 Matriz RF → fase → prueba

| RF | Fase | Prueba principal |
|---|---|---|
| RF-01 | F2 | Formulario y validación de límites |
| RF-02 | F4 | `menu_entries` = `days × 2` |
| RF-03 | F4 | Ticket ≤ presupuesto en menús guardados |
| RF-04 | F4 | Preview `infeasible` con mínimo, déficit y sugerencias |
| RF-05 | F2 | Exclusión persistente y filtrado |
| RF-06 | F2/F4 | Alérgenos fail-closed y presión de presupuesto |
| RF-07 | F2 | Contrato sin pasos de cocina |
| RF-08 | F4 | Suma de `shopping_items` = ticket |
| RF-09 | F3 | Despensa parcial antes de `ceil` |
| RF-10 | F4 | Bloqueo, swap y regeneración |
| RF-11 | F4 | CP, almacén y fecha visibles en UI y respuesta |
| RF-12 | F1 | Sync al arrancar y manual |
| RF-13 | F5 | Historial inmutable |
| RF-14 | F2 | Búsqueda de platos/productos |
| RF-15 | F3/F4 | Coste por comida/día/persona |
| RF-16 | F5 | Exportación, impresión y escape CSV |
| RF-17 | F4 | Mínimos diarios y variedad en 1/2/7/14 días |
| RF-18 | F0/F1 | CP 22002 y almacén 4389 |
| RF-19 | F3 | Valor de sobras |
| RF-20 | F2 | Validador de seed |
| RF-21 | F2 | `UNIQUE(product_id)` y test de producto compartido |
| RF-22 | F3 | Identidad contable |
| RF-23 | F4 | Recalculo y rechazo de swap caro |

---

## 20. Supuestos y backlog

### Supuestos

- Un solo usuario local, sin login.
- Interfaz en español; identificadores de dominio en inglés.
- Precios en EUR.
- Menú solo de comida y cena.
- 1-14 días y 1-10 personas.
- 50-60 platos iniciales.
- Sin dieta especial por defecto; sí exclusiones y alérgenos.
- Presupuesto total del periodo, no semanal obligatorio.
- Precios de la tienda online, no de tienda física.
- CP fijo 22002 / almacén 4389 en el MVP.

### Backlog posterior al MVP

- Cambio de CP y almacén desde la UI.
- Acceso desde móvil por LAN con autenticación.
- Arrastre de despensa y sobras entre menús.
- Historial de precios y gráficos.
- Alertas de bajadas de precio.
- Varios perfiles.
- Exportación PDF.
- PWA/offline.
- Docker y despliegue en VPS.
- Importar/exportar platos.
- Macros y calorías.
- Comparador de formatos y alternativas automáticas.
- Playwright E2E.
