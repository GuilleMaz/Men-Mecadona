# TASKS.md — Cesta

> **Estado global:** F0 en curso. F0.1, F0.2, F0.3, F0.4 y F0.5 completadas.
> **Última actualización:** 2026-10-25
> **Plan de referencia:** `PLAN.md`

## Convenciones

- `[ ]` pendiente · `[~]` en curso · `[x]` hecho · `[!]` bloqueado
- Cada tarea debe tener un resultado verificable.
- No se pasa a la siguiente fase sin cumplir el **Definition of Done (DoD)** de la actual.
- Al terminar una tarea: actualizar este archivo y `project-memory/`.
- No se implementan recetas ni pasos de cocina. El dominio usa **platos** (`dishes`).
- Las estimaciones son orientativas; se reestimarán después de F0.

---

## F0 — Fundaciones y spikes

**Objetivo:** esqueleto ejecutable y validación temprana de los dos riesgos técnicos: Mercadona y OR-Tools.

**Estimación:** 2-3 días.

- [x] **F0.1 — Estructura del repositorio**
  - Crear `backend/`, `frontend/`, `scripts/` (solo la estructura necesaria).
  - Añadir `.gitignore` para Python, Node, SQLite, `.env`, build y `node_modules`.
  - Crear `.env.example` con `APP_ENV`, `SYNC_ON_STARTUP` y `OPTIMIZER_TIME_LIMIT_SECONDS=8`. `CESTA_DATA_DIR` queda comentado como opcional y absoluto.
  - No crear una carpeta `data/` en la raíz: los YAML viven en `backend/app/data/` y la base en `%LOCALAPPDATA%\Cesta`.
  - Inicializar git y primer commit si el usuario lo autoriza.
  - **DoD:** árbol reproducible; no se versionan bases de datos ni dependencias.

- [x] **F0.2 — Backend mínimo y tooling**
  - Inicializar con `uv` y Python 3.13.
  - Dependencias: FastAPI, Uvicorn, Pydantic v2, pydantic-settings, SQLAlchemy, Alembic, httpx, tenacity, OR-Tools.
  - Dev: pytest, pytest-asyncio, respx, Ruff, mypy.
  - Crear `app/main.py`, `app/config.py`, `app/db.py`.
  - Endpoint `GET /api/health`.
  - Configurar CORS solo para `http://localhost:5173` en desarrollo.
  - **DoD:** `uv run uvicorn app.main:app --reload` responde `{"status":"ok"}`; `uv run pytest`, `ruff` y `mypy` **pasan en verde**.

- [x] **F0.3 — Frontend mínimo y tooling**
  - Inicializar Vite + React + TypeScript.
  - Instalar Tailwind CSS, shadcn/ui, TanStack Query, React Router, React Hook Form, Zod, Lucide.
  - Dev: Vitest, Testing Library, MSW, ESLint, Prettier.
  - Crear layout base en español con navegación: Menú, Platos, Ajustes.
  - Página de inicio con formulario placeholder.
  - **DoD:** `npm run dev` muestra la app; `npm run test`, `lint` y `build` funcionan.

- [x] **F0.4 — Cliente Mercadona mínimo**
  - Implementar `MercadonaClient` con httpx.
  - Fijar CP 22002 con `PUT /api/postal-codes/actions/change-pc/`.
  - Leer `x-customer-wh` y validar `4389`.
  - Descargar `/api/categories/` y una subcategoría.
  - Guardar fixtures **mínimas y sintéticas** (2-3 productos, una sección), no el catálogo completo.
  - **DoD:** script que imprime 26 secciones, ≥100 subcategorías, almacén 4389 y un producto parseado.

- [x] **F0.5 — Spike del catálogo**
  - Descargar las 152 subcategorías con concurrencia 4 y registrar:
    - número de productos únicos;
    - tiempo total;
    - productos sin precio;
    - productos no publicados;
    - categorías fallidas.
  - Comparar con los ~4.327 observados.
  - Guardar el informe en `project-memory/decisions.md`.
  - **DoD:** script `scripts/spike_catalog.py` reproducible; umbrales: ≥20 secciones, ≥100 subcategorías, ≥3.000 productos, precios parseables.

- [ ] **F0.6 — Spike de OR-Tools**
  - Instalar OR-Tools en Python 3.13/Windows.
  - Resolver un modelo toy con 28 huecos, 60 platos, 120 ingredientes y paquetes.
  - Medir tiempo y verificar `num_search_workers=1`.
  - Si falla, **elegir un único solver alternativo** (SciPy MILP o PuLP) y registrar la decisión; no mantener dos modelos en paralelo.
  - **DoD:** toy resuelto en <10 s o decisión única de cambio de solver documentada.

- [ ] **F0.7 — Arranque local y base de datos**
  - Crear `run.ps1` para desarrollo (backend + frontend).
  - Resolver `CESTA_DATA_DIR` a ruta absoluta; por defecto `%LOCALAPPDATA%\Cesta`.
  - Crear la base fuera de OneDrive.
  - Configurar SQLite con WAL, `foreign_keys=ON` y `busy_timeout=5000`.
  - Documentar `powershell -ExecutionPolicy Bypass -File .\run.ps1`.
  - **DoD:** `.\run.ps1` arranca ambos servicios; la base se crea fuera de OneDrive.

- [ ] **F0.8 — Seguridad local básica**
  - Bind a `127.0.0.1`.
  - CORS solo en desarrollo y solo para el puerto de Vite.
  - Validar cabecera `Host`.
  - Sin secretos en el repositorio.
  - **DoD:** checklist de seguridad local y test de que un origen no permitido no recibe CORS.

- [ ] **F0.9 — Scripts de calidad**
  - Añadir `check.ps1` o scripts npm/uv para lint, tipos y tests.
  - Documentar comandos en README futuro.
  - **DoD:** un comando ejecuta lint + tipos + tests de backend y frontend.

- [ ] **F0.10 — Smoke test**
  - Test de `/api/health`.
  - Test del cliente con fixture sintética, sin red.
  - Comprobar que el frontend consume `/api/health`.
  - **DoD:** tests verdes y app mostrando el estado del backend.

**DoD de F0:** esqueleto ejecutable, cliente Mercadona validado para 22002/4389, OR-Tools validado, base fuera de OneDrive y scripts de calidad.

---

## F1 — Catálogo y sincronización

**Objetivo:** descargar, normalizar y persistir el catálogo completo, con fallos parciales controlados.

**Depende de:** F0.

**Estimación:** 2-3 días.

- [ ] **F1.1 — Modelos de catálogo**
  - `Category`, `Product`, `SyncRun`, `SyncCategoryRun`, `ProductAllergen`.
  - `Product.external_id` con `UNIQUE` como clave natural de upsert; EAN informativo.
  - `Product.allergen_status` (`known|partial|unknown`).
  - Campos normalizados: `package_quantity_milli`, `package_unit`, `package_price_cents`, `reference_price_cents`, `reference_unit`.
  - Índices por `category_id`, `name`, `published`, `last_seen_at`.
  - Sin `raw_json` persistente ni `price_snapshots` en el MVP.
  - **DoD:** migración inicial crea las tablas.

- [ ] **F1.2 — Migraciones y SQLite**
  - Configurar Alembic con `render_as_batch=True`.
  - Activar `foreign_keys`, `busy_timeout` y WAL.
  - Documentar comando de migración.
  - **DoD:** base vacía → migración → tablas con constraints.

- [ ] **F1.3 — Normalizador de productos**
  - Parsear `unit_price`, `reference_price`, `unit_size`, `size_format`.
  - Convertir importes a céntimos y cantidades a milésimas de g/ml/unidad.
  - Detectar packs, peso aproximado y productos de mostrador.
  - Tests con aceite, huevos, pollo, leche y pack 6 × 125 g.
  - **DoD:** función pura testeada; nunca usa `float` para dinero.
  - **Regla:** `unit_price` de la API es precio del **paquete**, no precio por unidad base.

- [ ] **F1.4 — Servicio de sincronización**
  - Descargar secciones y subcategorías.
  - Concurrencia máxima 4; reintentos con backoff.
  - Upsert idempotente de productos por `external_id`.
  - Registrar éxito/fallo por subcategoría.
  - Marcar no disponible solo productos de subcategorías descargadas correctamente.
  - `sync_runs.status`: `success`, `partial`, `failed`.
  - Lock para no solapar syncs.
  - **DoD:** dos syncs consecutivos no duplican productos; una subcategoría fallida no marca sus productos como no disponibles.

- [ ] **F1.5 — Endpoints de catálogo**
  - `GET /api/catalog/status`
  - `POST /api/catalog/sync`
  - `GET /api/catalog/categories`
  - `GET /api/catalog/products?q=&category_id=&limit=&offset=`
  - `GET /api/catalog/products/{id}`
  - **DoD:** búsqueda por nombre y filtro por categoría funcionan; `raw_json` nunca se expone.

- [ ] **F1.6 — Sync al arrancar**
  - Si la base está vacía, sincronizar automáticamente.
  - Si la última sync tiene más de 24 h, refrescar en segundo plano.
  - Exponer progreso y estado parcial en `/api/catalog/status`.
  - **DoD:** primer arranque descarga el catálogo sin bloquear la UI.

- [ ] **F1.7 — UI de estado del catálogo**
  - Pantalla de ajustes con última sync, número de productos, estado y errores.
  - Botón “Actualizar catálogo”.
  - Polling de progreso.
  - **DoD:** el usuario puede ver y lanzar la sincronización.

- [ ] **F1.8 — Tests de catálogo**
  - Fixtures sintéticas de sección, subcategoría y producto.
  - Test de normalización, upsert, sync idempotente y fallo parcial.
  - **DoD:** tests sin red y cobertura de los casos críticos.

**DoD de F1:** base con ≥3.000 productos, precios de 22002, sync parcial robusta y búsqueda operativa.

---

## F2 — Ingredientes, platos, alérgenos y preferencias

**Objetivo:** construir el catálogo de platos sin recetas, los alérgenos y las preferencias del usuario.

**Depende de:** F1.

**Estimación:** 3-4 días.

- [ ] **F2.1 — Modelos de dominio**
  - `Ingredient`, `IngredientProduct` con `UNIQUE(product_id)`.
  - `Dish`, `DishIngredient`.
  - `Profile` (fila única), `Exclusion` con FKs separadas, CHECK SQL explícito y tres índices únicos parciales para evitar duplicados con NULL.
  - `PantryItem` con `quantity_milli`, sin columna `unit` redundante, y `UNIQUE(profile_id, ingredient_id)`.
  - **DoD:** migración aplicada y constraints activos; duplicado de exclusión rechazado.

- [ ] **F2.2 — Seed de ingredientes**
  - Crear `ingredients.yaml` con ~120 ingredientes.
  - Campos: slug, nombre, categoría, grupo, unidad base, `grams_per_unit`, `serving_group`, `serving_size_milli`, fuente de proteína, alérgenos y etiquetas.
  - **DoD:** todos los ingredientes tienen unidad base, grupo, ración y alérgenos declarados o `unknown`.

- [ ] **F2.3 — Mapeo ingrediente → producto**
  - 1-3 productos por ingrediente, con prioridad y producto por defecto.
  - Un producto pertenece a un solo ingrediente.
  - Validar contra el catálogo sincronizado.
  - **DoD:** cada ingrediente tiene al menos un mapeo; el validador falla si un producto se comparte.

- [ ] **F2.4 — Alérgenos**
  - Lista canónica: gluten, crustaceans, eggs, fish, peanuts, soybeans, milk, nuts, celery, mustard, sesame, sulphites, lupin, molluscs y `unknown`.
  - `product_allergens` con origen y confianza; `products.allergen_status` (`known|partial|unknown`).
  - Descargar detalle de producto solo para productos mapeados.
  - Política fail-closed: `P_i` solo incluye productos `known` sin alérgenos declarados; `partial`/`unknown` se excluyen si el usuario declara alérgenos.
  - Unión ingrediente/producto; si `P_i` queda vacío, el ingrediente y sus platos son inelegibles.
  - Producto de respaldo = siguiente elegible por prioridad.
  - **DoD:** los 14 códigos + `unknown` están cubiertos por tests; un producto `unknown` barato no entra con alérgeno declarado; un producto de respaldo con alérgeno tampoco.

- [ ] **F2.5 — Seed de platos y cobertura**
  - Crear `dishes.yaml` con 50-60 platos, sin pasos.
  - Slugs y enums en inglés; nombres en español.
  - Campos: `meal_types`, `protein_sources`, `has_vegetables`, `light`, `carbs`, etiquetas e ingredientes.
  - Derivar `has_vegetables`, `light`, `carbs` y `protein_sources` de la composición; el YAML se valida contra la derivación. `light` no usa “no frito”.
  - Cubrir los umbrales de `PLAN.md` §13.2.
  - **DoD:** ≥14 platos de comida, ≥14 de cena, ≥28 elegibles, ≥3 fuentes de proteína con ≥4 platos; flags coherentes con la composición.

- [ ] **F2.6 — Cargador de seed idempotente**
  - `SeedService.load()` con upsert por `slug` estable.
  - `seed_version` y soft delete de platos con menús históricos.
  - `--dry-run`.
  - **DoD:** dos cargas consecutivas no duplican ni borran datos; los cambios de YAML se reflejan.

- [ ] **F2.7 — Validador de seed y cobertura**
  - Script `scripts/validate_seed.py`.
  - Comprobar ingredientes, productos, precios, unidades, alérgenos, cobertura y `UNIQUE(product_id)`.
  - Comprobar que con las exclusiones por defecto quedan al menos `días × 2` platos para 14 días.
  - **DoD:** el seed actual pasa; los errores de prueba se detectan; la cobertura es medible.

  El dry-run del optimizador para 1, 2, 7 y 14 días y 1, 2, 4 y 10 personas se añade en F4.9, cuando el modelo existe.

- [ ] **F2.8 — API de platos y preferencias**
  - `GET /api/dishes`, `GET /api/dishes/{id}`.
  - `GET /api/allergens`.
  - `GET/PUT /api/profile`.
  - `GET/POST/DELETE /api/exclusions` (sin PUT).
  - `GET/PUT /api/pantry` con cantidades en unidad base.
  - **DoD:** se pueden listar platos, excluir ingredientes/platos/etiquetas, declarar alérgenos y guardar despensa.

- [ ] **F2.9 — UI de configuración**
  - Formulario inicial: personas, días, presupuesto.
  - Pantalla de ajustes: exclusiones, alérgenos, despensa, sync.
  - Catálogo de platos con búsqueda y filtros.
  - Botón “no me gusta” en plato o ingrediente.
  - **DoD:** las preferencias persisten y filtran el catálogo visible.

- [ ] **F2.10 — Tests de F2**
  - Filtrado por exclusión de ingrediente, plato y etiqueta.
  - Persistencia de perfil, alérgenos y despensa.
  - Validador con datos inválidos.
  - Producto compartido entre ingredientes.
  - Alérgeno `unknown` y producto de respaldo.
  - **DoD:** tests verdes y sin red.

**DoD de F2:** catálogo de platos validado, alérgenos fail-closed, usuario configurable y exclusiones funcionando.

---

## F3 — Motor de costes puro y preview

**Objetivo:** calcular el coste real con paquetes, despensa y sobras, sin depender todavía de menús persistidos.

**Depende de:** F2.

**Estimación:** 2-3 días.

- [ ] **F3.1 — Unidades y conversión**
  - `quantity_milli` en mg, µl o mili-unidades.
  - `grams_per_unit` para ingredientes por pieza.
  - Validar que plato y producto usan la misma unidad base.
  - **DoD:** casos dorados de huevos, cebolla, pollo y aceite.

- [ ] **F3.2 — Necesidad neta y despensa**
  - `net_need = max(0, need − pantry)`.
  - Despensa parcial, completa y sobre-despensa.
  - **DoD:** nunca se generan paquetes negativos; la necesidad neta se calcula antes de `ceil`.

- [ ] **F3.3 — Paquetes y plan de compra**
  - Implementar `plan_purchase(ingrediente, necesidad_neta)`: combinación de paquetes que minimiza coste total, permite mezclar formatos y desempata por menos paquetes, menor precio y `product_id`.
  - Calcular paquetes por producto.
  - Asignar consumo a formatos comprados por precio unitario ascendente.
  - Calcular sobras.
  - **DoD:** `used + leftover = purchased`; no hay doble conteo; `preview.ticket == shopping_list.ticket` para el mismo menú.

- [ ] **F3.4 — Identidad contable**
  - `ticket + pantry_consumption = consumption + leftover`.
  - Redondeo half-up solo al final.
  - **DoD:** test de identidad con despensa 0, parcial y total.

- [ ] **F3.5 — Endpoint de preview**
  - `POST /api/pricing/preview` con platos, personas y despensa.
  - No persiste menú ni aplica filtros de alérgenos; el preview es de coste.
  - Devuelve coste, ticket, consumo, despensa y sobras.
  - **DoD:** el preview coincide con el cálculo puro y no crea filas en `menus`; `preview.ticket == shopping_list.ticket` para el mismo conjunto de platos.

- [ ] **F3.6 — UI de coste en plato**
  - Mostrar coste de consumo por ración y por plato.
  - Mostrar ingredientes y productos asociados.
  - **DoD:** el coste cambia al actualizar precios o personas.

- [ ] **F3.7 — Tests de coste**
  - Aceite 5 L vs 1 L.
  - Huevos por unidades.
  - Pollo 500 g.
  - Pack 6 × 125 g.
  - 1 persona vs 4 personas.
  - Despensa parcial, completa y sobre-despensa.
  - `preview.ticket == shopping_list.ticket` para un menú fijo.
  - **DoD:** todos los casos documentados pasan.

**DoD de F3:** coste, ticket, despensa y sobras exactos y verificables; preview sin persistencia.

---

## F4 — Optimizador, menú y lista de la compra

**Objetivo:** generar el menú `días × 2` bajo presupuesto, permitir ajustes y materializar la lista.

**Depende de:** F3.

**Estimación:** 4-5 días.

- [ ] **F4.1 — Modelos de menú y migración**
  - `Menu`, `MenuEntry`, `MenuEntryIngredient`, `ShoppingItem`.
  - Snapshot de nombre de plato, coste de entrada, fuente de proteína y precios de compra.
  - `Menu`: `status`, `price_status`, `timed_out`, `revalidated_ticket_cents`, `settings_json` (`MenuSettings` con exclusiones, despensa, alérgenos, `max_repeats`, versión del optimizer).
  - `UNIQUE(menu_id, day_index, slot)` y `UNIQUE(menu_id, product_id)`.
  - **DoD:** migración aplicada; el historial no depende de platos vivos; el snapshot de preferencias es reproducible.

- [ ] **F4.2 — Filtro de elegibilidad**
  - Excluir por ingrediente, plato, etiqueta, alérgeno y producto no disponible.
  - Fail-closed: `P_i` solo productos `known`; `partial`/`unknown` fuera si el usuario declara alérgenos; si `P_i` queda vacío, el ingrediente y sus platos son inelegibles.
  - Informar de platos elegibles y de ingredientes bloqueados.
  - **DoD:** ninguna exclusión ni alérgeno aparece en la solución; un producto `unknown` barato no entra con alérgeno declarado.

- [ ] **F4.3 — Modelo CP-SAT**
  - Variables `x`, `q` y `violation[k]` (entero no negativo).
  - Coeficiente por plato: `coef[r,i] = round(quantity_milli[r,i] × people / base_servings[r])`.
  - Demanda: `Σ_{p∈P_i} q[p] × package_quantity_milli[p] + pantry_milli[i] ≥ Σ_{r,d,s} coef[r,i] × x[r,d,s]`.
  - Restricciones duras: un plato por hueco, compatibilidad `lunch`/`dinner`, exclusiones, alérgenos, presupuesto, repeticiones, bloqueos, mínimos diarios por persona y `UNIQUE(product_id)`.
  - `used`/`leftover` son post-cálculo, no variables.
  - **DoD:** resuelve 7 días/2 personas y 14 días/4 personas; test con platos de distinto `base_servings` que comparten ingrediente.

- [ ] **F4.4 — Objetivo lexicográfico e inviabilidad**
  - Etapa 1: minimizar `Σ violation[k]` (peso 1).
  - Etapa 2: fijar la suma óptima y minimizar ticket.
  - Si la etapa 1 agota el tiempo sin prueba de optimalidad, usar el incumbente, mejorar en la etapa 2 y devolver `feasible`.
  - Inviabilidad con `reason ∈ {budget, repeats, minimums, locks, no_assignment}`.
  - Solo `budget` produce preview `infeasible` con `is_preview=true`, mínimo estimado, `minimum_is_estimate`, `shortfall_cents` y sugerencias; no se persiste.
  - Las demás causas devuelven `422 NO_FEASIBLE_MENU`.
  - **DoD:** menú más barato con variedad 0; si no cabe, mínimo + déficit + sugerencias; nunca se relaja el presupuesto ni un alérgeno.

- [ ] **F4.5 — Servicio de menús, plan de compra y recálculo**
  - Persistir menú, `MenuSettings`, entradas y compras.
  - Materializar `shopping_items` con `plan_purchase` sobre la necesidad agregada; verificar `ticket_canónico ≤ ticket_solver ≤ budget`.
  - Verificar `Σ menu_entry_ingredients = entry_consumption` y `Σ entries = consumption`.
  - Recalcular ticket, lista y costes tras swap, exclude, regenerate, revalidate o “ya lo tengo”.
  - Rechazar cambios que superen presupuesto; `regenerate` con bloqueos inviable devuelve `reason="locks"`.
  - Conservar `checked` por `product_id` si el producto sigue.
  - **DoD:** `ticket == Σ shopping_items.subtotal`; un swap caro devuelve `BUDGET_EXCEEDED`; `preview.ticket == shopping_list.ticket` para el mismo menú.

- [ ] **F4.6 — API de menús**
  - `POST /api/menus/generate`
  - `GET /api/menus` paginado, `GET /api/menus/{id}`
  - `PATCH .../entries/{id}` solo `locked` (bloquear/desbloquear)
  - `POST .../entries/{id}/swap`
  - `POST .../entries/{id}/exclude` con `scope=menu|profile`
  - `POST .../regenerate`
  - `POST .../revalidate`
  - `GET .../shopping-list`
  - `PATCH .../shopping-list/items/{id}`
  - `GET .../export`
  - **DoD:** flujo completo por API; contrato de estados/errores tipado; `404 NOT_FOUND` para recursos inexistentes.

- [ ] **F4.7 — UI del menú**
  - Rejilla días × comida/cena.
  - Tarjetas con coste, etiquetas y acciones.
  - Barra de presupuesto.
  - Modal de menú inviable con mínimo, déficit y sugerencias.
  - Mostrar fecha de precios, CP y almacén.
  - Acciones: bloquear/desbloquear, cambiar, no me gusta, regenerar.
  - Estados: generando, óptimo, factible, relajado, inviable, sin platos, timeout, error, `stale`.
  - **DoD:** se puede generar, cambiar, bloquear/desbloquear y regenerar desde la UI; CP/almacén/fecha visibles.

- [ ] **F4.8 — Lista de la compra UI**
  - Agrupación por secciones.
  - Checkboxes y “ya lo tengo”.
  - “Ya lo tengo” actualiza el snapshot de despensa del menú y recalcula; no muta la despensa global.
  - Total sticky, sobras y coste por comida/día/persona.
  - **DoD:** la lista coincide con la API; `ticket == Σ subtotales`; identidad contable visible.

- [ ] **F4.9 — Tests del optimizador y del menú**
  - 1, 2, 3, 7 y 14 días.
  - 1, 2, 4 y 10 personas.
  - Presupuesto exacto, ajustado e imposible.
  - Exclusión de pescado, alérgeno `unknown`, producto compartido.
  - Bloqueos, desbloqueos y regeneración.
  - Swap que supera presupuesto.
  - Mínimos diarios y variedad de RF-17 en 1/2/7/14 días.
  - Platos con `base_servings` distintos que comparten ingrediente.
  - `preview.ticket == shopping_list.ticket`.
  - Optimalidad con fuerza bruta en instancia pequeña.
  - Dry-run de 1/2/7/14 días y 1/2/4/10 personas.
  - `num_search_workers=1` y semilla fija.
  - **DoD:** tests verdes; generación p95 < 10 s con 20 ejecuciones en el equipo de desarrollo.

**DoD de F4:** menú completo, bajo presupuesto, con ajustes, lista exacta y explicaciones.

---

## F5 — Calidad, seguridad y entrega

**Objetivo:** dejar la app usable, documentada, segura y probada.

**Depende de:** F4.

**Estimación:** 2-3 días.

- [ ] **F5.1 — Resiliencia y deriva de precios**
  - Fallback a última copia solo si su `warehouse=4389` y `postal_code=22002`; sirve para consultar menús guardados, no para generar nuevos.
  - Si la copia es de otro almacén, no se usa para precios actuales.
  - Banner de precios desactualizados con delta.
  - Revalidar ticket y lista al abrir un menú guardado con `POST /api/menus/{id}/revalidate`.
  - Marcar `price_status="stale"` y ofrecer recalcular/regenerar.
  - **DoD:** la app sigue operativa sin red; un precio que sube no rompe la promesa sin aviso; no se mezclan almacenes.

- [ ] **F5.2 — Responsive, accesibilidad, privacidad e historial**
  - Revisar formularios, menú y lista en 1280 px y 768 px.
  - Lista imprimible en A4.
  - Revisión de teclado, foco, contraste y labels.
  - Test de que no hay telemetría ni envío de datos personales.
  - Historial de menús con nombre y coste congelados.
  - **DoD:** flujo completo usable; checklist de accesibilidad y privacidad sin fallos críticos; historial inmutable.

- [ ] **F5.3 — Exportación y seguridad**
  - Export markdown/CSV.
  - Escapar fórmulas CSV (`= + - @`).
  - Test de exportación y de inyección CSV.
  - CORS de producción desactivado, `Host` validado.
  - `pip-audit` / `npm audit`, lockfiles; cero hallazgos `high`/`critical`.
  - Backup/restore de SQLite.
  - **DoD:** checklist sin hallazgos high/critical; backup restaurado en prueba; test de exportación verde.

- [ ] **F5.4 — Documentación**
  - README con instalación, uso, arquitectura y limitaciones.
  - Aviso legal, alérgenos y precios.
  - Capturas o descripción de pantallas.
  - **DoD:** una persona puede arrancar la app siguiendo el README.

- [ ] **F5.5 — Rendimiento**
  - Índices y consultas críticas.
  - Medir sync, generación y endpoints.
  - Benchmark de generación con 14 días/4 personas, 20 ejecuciones, en el equipo de desarrollo.
  - **DoD:** sync < 2 min; generación p95 < 10 s (solver 8 s); `/api/dishes` < 200 ms.

- [ ] **F5.6 — Build local**
  - `npm run build`.
  - FastAPI sirve el frontend compilado.
  - `run.ps1 -Prod`.
  - **DoD:** un solo proceso sirve app y API.

- [ ] **F5.7 — Tests de integración y privacidad**
  - Flujo: crear menú → ver menú → lista.
  - Test de API con base temporal.
  - Test de contrato “sin pasos de cocina”.
  - Test de que no hay telemetría ni llamadas a servicios externos no declarados.
  - **DoD:** flujo principal cubierto; privacidad verificada.

**DoD de F5:** MVP instalable, documentado, seguro y probado.

---

## Backlog posterior al MVP

- [ ] Cambio de CP/almacén desde la UI y re-sync.
- [ ] Acceso desde móvil por LAN con autenticación.
- [ ] Arrastre de despensa y sobras entre menús.
- [ ] Historial de precios con gráficos.
- [ ] Alertas de bajadas de precio.
- [ ] Varios perfiles.
- [ ] Exportación PDF.
- [ ] PWA/offline.
- [ ] Docker y despliegue en VPS.
- [ ] Importar/exportar platos.
- [ ] Macros y calorías.
- [ ] Playwright E2E.
- [ ] Comparador de formatos y alternativas automáticas.

---

## Registro de bloqueos

| Fecha | Tarea | Bloqueo | Acción |
|---|---|---|---|
| 2026-10-25 | F4 | OR-Tools no validado todavía | F0.6 debe resolverlo antes de F4 |
| 2026-10-25 | F2 | Seed y mapeo dependen del catálogo real | F0.5 y F1 deben cerrarse antes |
