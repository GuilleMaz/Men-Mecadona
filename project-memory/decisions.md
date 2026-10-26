# Decisions

## 2026-10-26 — Menús persistidos, CP-SAT y lista canónica (F4.1-F4.5)

### Problema

F4 debía convertir el coste puro de F3 en menús persistidos, con snapshots
reproducibles, optimización bajo presupuesto y una lista que no pudiera
contradecir al solver. Había que decidir cómo separar elegibilidad, modelo,
inviabilidad y materialización, y cómo evitar que un swap o una revalidación
rompieran las identidades contables o el presupuesto.

### Decisión

- Migración `20261026_0003` con `menus`, `menu_entries`, `menu_entry_ingredients`
  y `shopping_items`; `20261026_0004` añade `violations`,
  `relaxation_codes_json` y el CHECK `ticket_cents <= budget_cents`.
  `Menu.settings_json` guarda un `MenuSettings` validado y versionado; el nombre
  del plato, el coste de entrada, la fuente de proteína y los precios de paquete
  quedan congelados. Las FKs a platos y productos son `RESTRICT` para que el
  historial no dependa de datos vivos.
- `app/services/optimizer.py` no abre sesiones: recibe `DishEligibility` ya
  evaluadas y devuelve asignaciones, paquetes, estado y diagnóstico. Solo usa
  productos de `P_i`, construidos desde `IngredientEligibility.eligible_products`.
- Modelo CP-SAT con `x`, `q` y seis violaciones de variedad. Los coeficientes se
  calculan con `scale_quantity` (half-up por plato). Las cotas de `q` son
  `ceil(max_need / package_quantity)` sin `+1`, la demanda incluye despensa, el
  presupuesto es duro y los mínimos diarios exigen una ración por persona.
- Para que un presupuesto ajustado no acabe en `timeout`, la etapa 1 recibe una
  pista greedy determinista: enumera parejas de platos por día, elige la más
  barata que cubre los mínimos y valora la compra con `plan_purchase`. Si la
  etapa 1 agota el tiempo, el fallback sin presupuesto devuelve un menú válido
  cuando su plan canónico cabe; el mínimo del preview `infeasible` se calcula
  también con `plan_purchase`, no con las `q` arbitrarias del fallback.
- Etapa 1: minimizar la suma de violaciones. Etapa 2: fijar esa suma y minimizar
  el ticket con `AddHint` del incumbente. `optimal` solo si ambas etapas prueban
  optimalidad; `feasible` si hay solución sin prueba; `relaxed` si la solución
  viola variedad; `timeout` si no hay incumbente.
- Inviabilidad: solo el presupuesto devuelve preview `infeasible` con mínimo,
  `minimum_is_estimate`, déficit y sugerencias. `locks`, `repeats`, `minimums` y
  `no_assignment` se diagnostican con solves cortos y lanzan
  `NO_FEASIBLE_MENU`. Nunca se relajan presupuesto, alérgenos ni exclusiones.
- `MenuService` es la única puerta de escritura. Materializa la lista con
  `plan_purchase` sobre la necesidad agregada, limita los formatos a `P_i`,
  valida que la sync sea de 22002/4389, reparte el consumo por entrada con
  `allocate_cents` y verifica `ticket_canónico ≤ ticket_solver ≤ budget` y las
  sumas de PLAN §6.2.
- `checked` se conserva por `product_id`; `pantry_quantity_milli` se guarda una
  sola vez por ingrediente para no duplicar la despensa al sumar líneas. Los
  recálculos usan `menu_entry_ingredients.used_milli` como snapshot de
  composición, no la composición viva del plato.
- `revalidate` recalcula precios sin romper el invariante: si el ticket nuevo
  supera el presupuesto, conserva la lista y el ticket válidos, guarda el nuevo
  valor en `revalidated_ticket_cents` y marca `stale`. Swap, exclude, regenerate
  y «ya lo tengo» sí revierten con `BUDGET_EXCEEDED`. `regenerate` propaga
  `reason="locks"` cuando los bloqueos hacen inviable el menú.

### Justificación

- Separar optimizador y persistencia permite testear el modelo sin base de datos
  y garantizar que la lista final no depende de los paquetes arbitrarios del
  solver.
- El snapshot de preferencias y de composición hace reproducible un menú aunque
  cambien el perfil, los platos o los precios.
- La lista canónica es la única forma de cumplir `preview.ticket == shopping_list.ticket`
  y `ticket == Σ shopping_items.subtotal` sin dobles criterios.
- Los diagnósticos con solves cortos solo se ejecutan cuando el modelo principal
  es inviable; no penalizan el camino normal.

### Alternativas

- Materializar la lista con los `q` del solver: descartado; podía sobrecomprar y
  no coincidir con F3.
- Recalcular con `ceil` sobre el producto por defecto: descartado; podía superar
  el presupuesto.
- Un objetivo escalar con penalizaciones: descartado; no garantiza variedad.
- Persistir previews de presupuesto: descartado; rompe la promesa de menú válido.
- Filtrar alérgenos solo al generar: descartado; la lista y los recálculos
  también deben respetar `P_i`.

### Resultado

- 270 tests backend en verde, sin red; `ruff`, formato y `mypy` strict en verde.
- `alembic check` sin deriva; migraciones `0003` y `0004` aplicadas a la copia
  local real.
- Smoke real con la copia del catálogo: menú de 1 día/2 personas, ticket 13,50 €,
  consumo 5,25 €, sobras 8,25 € e identidad correcta.
- 7 días/2 personas: `feasible` en 3,59 s con 70 € y 49,85 €; `feasible` con
  50 € y 42 € (41,05 € y 40,10 €); con 45 € devolvió `relaxed` (40,25 €, una
  violación de pescado) por el límite de tiempo. 14 días/4 personas en 3,74 s
  (111,83 €). Presupuesto de 1 €: preview `infeasible` con mínimo canónico
  45,40 € y déficit 44,40 €. Los tickets exactos pueden variar entre ejecuciones
  limitadas por reloj; lo estable es el estado, el presupuesto y la validez.
- La pista greedy y el fallback evitan los `timeout` que aparecían con
  presupuestos ajustados antes de la revisión.

### Limitaciones conocidas

- Los diagnósticos de inviabilidad usan solves cortos; un `UNKNOWN` en un
  diagnóstico se trata como no concluyente y el `reason` puede quedarse en
  `no_assignment`/`budget` si no hay prueba mejor.
- `verify_identities` es un método de comprobación pero, si falla, revierte la
  transacción actual; los llamadores de escritura ya lo invocan antes del commit
  y los de solo lectura no deben usarlo con cambios pendientes.
- `exclude` con `scope="menu"` persiste el plato en `settings_json` para que
  `regenerate` lo respete; sustituye todas las apariciones, incluidas las
  bloqueadas. Es una decisión de producto revisable en F4.6.
- Si la despensa cubre un ingrediente entero no hay línea de compra para ese
  ingrediente; la UI deberá mostrar la despensa desde `settings_json` y
  `pantry_consumption_cents`.
- `MenuSettings.version` no tiene migrador todavía; una versión futura deberá
  despachar por versión en `MenuService._settings`.
- El CHECK de presupuesto y la validación de sync son la red de seguridad; la
  API de F4.6 debe seguir pasando `sync_run_id` y mapear `WAREHOUSE_UNAVAILABLE`.

---

## 2026-10-26 — Motor de costes exacto, plan de compra y preview (F3)

### Problema

F3 debía calcular un ticket verificable con paquetes, despensa y sobras antes de
que existan menús persistidos. El redondeo de unidades y céntimos podía romper
la identidad contable, y el preview y la futura lista de F4 podían usar
criterios de compra distintos.

### Decisión

- `app/services/pricing.py` concentra funciones puras: `scale_quantity`,
  `scale_dish`, `purchasable_formats`, `plan_purchase`, `price_ingredient` y
  `price_basket`.
- Cantidades en milésimas de unidad base y céntimos enteros. `Decimal` se usa
  solo para costes unitarios intermedios; el redondeo half-up se aplica una vez
  por ingrediente y otra por ración mostrada.
- `plan_purchase` es exacto: enumera los formatos no óptimos con la cota
  `s_best / gcd(s_i, s_best)` y completa con el formato de menor coste unitario.
  Si el número de combinaciones es enorme, usa programación dinámica sobre el
  mcd de los tamaños. Desempata por coste, número de paquetes y `product_id`.
- La despensa se resta antes de comprar (`net_need`). Se valora al coste
  unitario del formato elegible más barato; si no hay compra, al producto por
  defecto. El consumo comprado se asigna a los formatos comprados por coste
  unitario ascendente. El valor de las sobras es el residuo exacto
  `ticket − consumo_comprado` para garantizar la identidad.
- El consumo de cada ingrediente se reparte entre las apariciones del plato con
  el método del mayor resto; la suma por entrada coincide con el total.
- `POST /api/pricing/preview` no persiste nada y no aplica filtros de alérgenos.
  Usa la despensa del perfil salvo que la petición envíe una explícita. Si un
  ingrediente no tiene producto comprable, devuelve 409 `PRODUCT_UNAVAILABLE`.
- `grams_per_unit` pasa a ser obligatorio para ingredientes con
  `base_unit=unit`.

### Justificación

- La identidad contable es un requisito Must y debe cumplirse por ingrediente,
  no solo en el total.
- La enumeración con cota es exacta y rápida con los 1-3 formatos reales; la
  programación dinámica cubre catálogos anómalos sin añadir un solver externo.
- Compartir `plan_purchase` entre preview y lista evita que F4 muestre un ticket
  distinto para el mismo menú.
- El preview de coste no debe ocultar platos por alérgenos: la UI de F2 ya
  explica la elegibilidad y F4 aplica el filtro estricto al generar.

### Alternativas

- Fuerza bruta completa sobre todos los paquetes: descartada por crecimiento con
  necesidades grandes.
- CP-SAT por ingrediente: descartado por coste de construcción y por no
  necesitar un solver para 1-3 formatos.
- Redondear cada línea de consumo: descartada; rompe la identidad por céntimos.
- Valorar siempre la despensa al producto por defecto: descartada; la regla
  acordada usa el formato más barato cuando hay compra.
- Aplicar alérgenos en el preview: descartado; el preview es de coste y el
  contrato lo separa de la generación.

### Resultado

- 20 tests puros, 11 de API y 1 de seed; identidad verificada con despensa 0,
  parcial, completa y sobre-despensa.
- Smoke manual con la copia local real (3 platos): ticket 22,85 €, consumo
  4,48 €, sobras 18,37 € e identidad correcta.

---

## 2026-10-26 — Seed, mapeo explícito y cobertura de F2

### Problema

El catálogo de Mercadona cambia entre syncs y muchos productos frescos tienen
peso variable. Había que construir ~120 ingredientes y 50-60 platos sin recetas,
garantizar que cada ingrediente tuviera al menos un producto comprable y que el
seed pudiera recargarse sin duplicar ni perder datos de usuario.

### Decisión

- `ingredients.yaml` incluye el mapeo explícito a 1-3 productos por ingrediente,
  con `external_id`, `priority` e `is_default`. No se mapea por heurística de
  nombre.
- Solo se aceptan productos fijos: `package_quantity_milli>0`,
  `package_price_cents>0`, `package_unit` compatible con la unidad base,
  `approx_size=False` y `selling_method=0`.
- `dishes.yaml` contiene composición, no pasos. `has_vegetables`, `light`,
  `carbs`, `protein_sources` y las etiquetas requeridas se derivan de la
  composición; el YAML se compara con la derivación y falla si no coincide.
- `SeedService` hace upsert por `slug`, preserva IDs de mapeos y componentes y
  usa `seed_version` = hash de los dos YAML. Los elementos ausentes se marcan
  `active=False` (soft delete). `--dry-run` revierte la transacción.
- `scripts/validate_seed.py` valida estructura, cobertura y catálogo real;
  `scripts/load_seed.py` permite cargar o simular la carga.

### Justificación

- El mapeo explícito es revisable y evita asignar un producto a un ingrediente
  equivocado por parecido de nombre.
- Excluir peso variable evita precios y cantidades que no se pueden garantizar.
- El hash de versión permite saber qué seed generó un plato y reproducir la
  carga; el soft delete no rompe futuros menús históricos.
- La derivación de flags evita etiquetas subjetivas y mantiene la coherencia con
  la composición.

### Alternativas

- Mapear por búsqueda de nombre/categoría: descartado por fragilidad.
- Incluir productos `approx_size`: descartado; el precio del paquete no es
  estable y el ticket dejaría de ser verificable.
- Borrar filas ausentes del seed: descartado; rompería referencias históricas.
- Guardar los flags solo en el YAML: descartado; no se podrían validar contra la
  composición.

### Resultado

- 110 ingredientes, 212 mapeos únicos, 60 platos (30 de comida, 45 de cena, 19
  cenas ligeras). `validate_seed.py` pasa con 0 avisos.
- Dos cargas consecutivas conservan conteos e IDs; el dry-run no persiste.

---

## 2026-10-26 — Alérgenos: `x99`, parser y fail-closed

### Problema

La API de Mercadona devuelve los alérgenos en HTML y usa `x99` cuando no hay una
declaración explícita. Algunos productos mencionan un alérgeno en los
ingredientes sin listarlo en el campo de alérgenos. Ignorar esos casos podía
introducir un alérgeno declarado por el usuario en un menú.

### Decisión

- `AllergenSyncService` descarga solo el detalle de los productos mapeados (212),
  con concurrencia 4 y sin persistir el JSON completo.
- El parser normaliza HTML y acentos, interpreta `Contiene`/`Puede contener` y
  busca alérgenos también en la lista de ingredientes. `x99` sin ingredientes es
  `unknown`; `x99` con ingredientes limpios es `known`; si los ingredientes
  contradicen la declaración, el producto queda `partial`.
- `product_allergens` guarda origen (`api`/`ingredients`) y confianza.
- Política fail-closed: con alérgenos declarados, `P_i` solo incluye productos
  `known` sin alérgeno coincidente. `partial`/`unknown` no entran. La unión
  ingrediente/producto es la fuente de verdad.
- Si `P_i` queda vacío, el ingrediente y sus platos son inelegibles; el producto
  de respaldo es el siguiente elegible por prioridad, nunca uno con alérgeno.

### Justificación

- Es un requisito de seguridad y legal; “cuando sea posible” no es aceptable.
- La lista de ingredientes permite detectar incoherencias sin inventar datos.
- El estado `partial` hace visible la incertidumbre y la excluye cuando importa.

### Alternativas

- Tratar `x99` siempre como “sin alérgenos”: descartado; podía ocultar alérgenos
  declarados solo en los ingredientes.
- Tratar `x99` siempre como `unknown`: demasiado restrictivo para alimentos
  básicos como patata o arroz.
- Confiar solo en el campo de alérgenos: descartado; el caso de los sulfitos en
  garbanzos demuestra que puede estar incompleto.
- Filtrar solo a nivel de plato: insuficiente si cambia el producto elegido.

### Resultado

- 212 productos mapeados: 212 actualizados en la prueba aislada y 210 en la base
  real (2 fallos transitorios reintentables); 11-12 `unknown`, 29 `partial`.
- Tests de los 14 códigos, `unknown`, unión, respaldo, producto barato desconocido
  y producto de respaldo con alérgeno.

---

## 2026-10-26 — Elegibilidad de platos reutilizable

### Problema

La UI de F2 y el optimizador de F4 necesitan el mismo criterio de elegibilidad.
Duplicarlo podía hacer que el catálogo visible y el menú generado discreparan.

### Decisión

- `app/services/eligibility.py` centraliza `PreferenceSnapshot`,
  `ingredient_eligibility`, `evaluate_dish` y `evaluate_dishes`.
- `GET /api/dishes` devuelve `eligible` y `exclusion_reasons`, y acepta
  `only_eligible`. La UI oculta los no elegibles por defecto, con opción de
  mostrarlos.
- Los motivos son códigos estables (`dish_excluded`, `tag_excluded`,
  `ingredient_excluded`, `ingredient_allergen`, `no_eligible_product`).

### Justificación

- Un único criterio para UI, tests y F4.2.
- La UI puede explicar por qué un plato no aparece sin duplicar reglas.
- El optimizador podrá reutilizar la misma función sin cambiar contratos.

### Alternativas

- Filtrar solo en el frontend: descartado; el catálogo visible y el menú podían
  discrepar.
- Filtrar en el endpoint y no exponer motivos: peor UX y más difícil de testear.

### Resultado

- Tests de exclusión por ingrediente, plato y etiqueta, alérgeno intrínseco y
  producto desconocido.

---

## 2026-10-26 — Catálogo: upsert idempotente, fallo parcial y sync en segundo plano

### Problema

La sincronización debía descargar ~4.300 productos con una API no oficial que
devuelve 403 transitorios y fallos aislados, sin duplicar filas, sin bloquear la UI
y sin ocultar productos de categorías que no se han podido descargar. Además, la
base necesitaba un esquema reproducible y migrable.

### Decisión

- Alembic con `render_as_batch=True`; una migración inicial
  (`20261026_0001`) crea las cinco tablas del catálogo. `run.ps1` ejecuta
  `alembic upgrade head` antes de arrancar el backend.
- `products.external_id` es la clave natural de upsert (TEXT, UNIQUE). Se usa el
  upsert por lotes de SQLite (`ON CONFLICT DO UPDATE`) y se conserva
  `first_seen_at`; no se persiste `raw_json`.
- La sync descarga primero el árbol de categorías, hace upsert de secciones y
  subcategorías y después descarga las subcategorías con concurrencia máxima 4.
- Cada subcategoría se registra en `sync_category_runs`. El estado global se
  calcula al final: `success` si no falla ninguna, `partial` si falla alguna y
  `failed` si fallan todas.
- Solo se marca `published=False` a productos ausentes de subcategorías
  descargadas correctamente, en un barrido final. Una subcategoría fallida no toca
  la disponibilidad de sus productos.
- Un lock de proceso impide solapar syncs. El POST devuelve `202` y la sync corre
  en `asyncio.create_task`; el arranque la lanza en segundo plano si el catálogo
  está vacío o la última copia tiene más de 24 h.
- `GET /api/catalog/status` expone `is_syncing`, conteos, última sync, error y
  progreso (`categories_ok + categories_failed` sobre el total actual).
- Al arrancar se marcan como `failed` las syncs que quedaron `running` por un
  reinicio.

### Justificación

- El upsert evita duplicados y conserva la identidad de los productos entre syncs.
- El fallo parcial es el modo normal de una API no oficial; borrar o marcar todo
  como no disponible por una categoría fallida rompería la promesa de catálogo.
- El progreso persistido permite polling real desde Ajustes.
- No bloquear el startup evita que la primera apertura parezca colgada.
- `alembic check` no detecta deriva entre modelos y migración.

### Alternativas

- Reemplazar el catálogo completo en una transacción: descartado; un fallo parcial
  dejaría la base vacía o incompleta.
- Sync secuencial: descartado; el spike mostró ~65 s frente a 7,74 s con
  concurrencia 4.
- Bloquear el arranque hasta terminar la sync: descartado; la UI debe abrir aunque
  no haya red.
- Celery/Redis para la sync: descartado por stack y por ser una app local de un
  proceso.
- Lock en base de datos con índice único parcial: descartado para el MVP; el lock
  de proceso cubre el único worker de `run.ps1`.

### Resultado

- Sync real del 2026-10-26: 152/152 subcategorías, 4.540 productos vistos, 4.288
  únicos, 178 categorías, 7,74 s, estado `success`, CP 22002 / almacén 4389.
- La diferencia con los 4.291 del spike de F0.5 (−3) entra dentro de la variación
  normal de disponibilidad de la tienda.

---

## 2026-10-26 — Normalización monetaria y de unidades del catálogo

### Problema

La API mezcla precios de paquete, precios de referencia y cantidades con formatos
como `l`, `ml`, `kg`, `g`, `ud` o `pack_size` decimal. Usar `float` para dinero o
guardar un «precio por gramo» en céntimos haría imposible garantizar el ticket.

### Decisión

- Importes con `Decimal` y redondeo half-up a céntimos enteros; nunca `float` para
  dinero. Se aceptan coma y punto decimal y se rechazan importes malformados.
- `unit_price` se interpreta como precio del **paquete**, no por unidad base.
- `package_quantity_milli` se guarda en milésimas de la unidad base (`mg`, `µl` o
  mili-unidades) y `package_unit` es `g`, `ml` o `unit`.
- `reference_price_cents` y `reference_unit` conservan el precio de referencia
  (`kg`, `l`, `g`, `ml` o `unit`) para comparar formatos.
- Si `unit_size` falta y el producto es un pack con `pack_size × total_units`, se
  deriva la cantidad y se marca `is_estimated=True`.
- Un formato desconocido deja `package_quantity_milli=NULL`: el producto existe,
  pero F2.3 no lo mapea.
- `approx_size=True` o `selling_method != 0` identifican mostrador/peso variable y
  quedan fuera del mapeo.
- `is_food` se deriva con una heurística conservadora sobre nombres de sección y
  subcategoría (limpieza, higiene, mascotas, etc.); el mapeo real de ingredientes
  seguirá siendo explícito en F2.3.

### Justificación

- Los céntimos y las milésimas son enteros y encajan con CP-SAT y SQLite.
- Evita arrastrar errores de coma flotante al ticket y a la identidad contable.
- No inventa cantidades cuando la API no ofrece un formato reconocible.

### Alternativas

- Guardar precios como `float`: descartado por la regla del proyecto.
- Parsear cantidades del nombre del producto: descartado; frágil y no verificable.
- Guardar el precio de referencia por gramo en céntimos: descartado; se recalcula
  desde el paquete.

### Resultado

- Casos dorados de aceite 5 L, huevos, pollo 500 g, leche 1 L y pack 6 × 125 g.
- Productos de mostrador detectados y excluidos del mapeo futuro.

---

## 2026-10-26 — Cierre de fase con commit y push obligatorio

### Problema

El trabajo de una fase podía quedar en el árbol de trabajo sin commitear o sin
subir a GitHub. Eso rompe la trazabilidad, deja fases "hechas" solo en local y
facilita que se mezclen cambios de varias fases.

### Decisión

- `finish-phase.ps1` es el único gate de cierre de fase.
- Ejecuta `check.ps1` antes de commitear; si la calidad falla, no hay commit.
- Rechaza archivos prohibidos (`*.db`, `.env` distintos de `.env.example`,
  `node_modules`, `.venv`, `frontend/dist`, claves privadas).
- Crea un commit `FASE: resumen` y lo sube a `origin` (o al remoto indicado).
- Si el push falla, el commit queda local y el script termina con error.
- `AGENTS.md` y `TASKS.md` exigen usar el script al cerrar cada fase; el DoD
  incluye commit y push.
- `-NoPush` y `-SkipChecks` existen solo como escapes documentados; no son el
  flujo normal.

### Justificación

- Un comando reproducible convierte el cierre en parte del pipeline, no en una
  acción manual fácil de olvidar.
- El orden calidad → commit → push evita subir código roto.
- El filtro de archivos prohibidos protege secretos y datos locales.
- El fallo del push no destruye el commit; se puede reintentar.

### Alternativas

- GitHub Actions que haga commit tras cada fase: descartado. El CI no sabe cuándo
  una fase está terminada y necesitaría un token con permisos de escritura,
  además de arriesgar bucles de commits.
- Commit manual con `git commit && git push`: descartado. No garantiza que se
  ejecute la calidad ni que el push se complete.
- Hook `pre-push` que ejecute los tests: útil como refuerzo, pero no sustituye al
  gate de cierre ni crea el commit.

---

## 2026-10-26 — Informe del spike de OR-Tools (F0.6)

### Ejecución

- Script: `scripts/spike_ortools.py`.
- Comando: `cd backend; uv run python ..\scripts\spike_ortools.py` (3 repeticiones).
- Entorno: Windows, Python 3.13.5, OR-Tools 9.15.6755.
- Modelo: 14 días × 2 huecos = 28 huecos; 60 platos; 120 ingredientes; 240 productos/paquetes; 4 personas.
- Presupuesto: 358,16 €; menú de referencia: 341,10 €.
- Solver: `num_search_workers=1`, `random_seed=42`; etapa 1: 3 s; etapa 2: 3 s.
- Cobertura sintética: 40 verduras, 30 proteínas de 9 fuentes, 25 hidratos de 4 fuentes y 25 extras; despensa, dos bloqueos, mínimos diarios y variedad.

### Resultado

| Métrica | Valor |
|---|---|
| Repeticiones | 3 |
| Etapa 1 | `OPTIMAL`, 0 violaciones, 0,28-0,29 s |
| Etapa 2 | `FEASIBLE`, ticket 333,18 €, 3,00 s |
| Total por repetición | 3,46-3,47 s |
| Validación | 28 huecos, demanda, mínimos, variedad, presupuesto y bloqueos OK |
| DoD (<10 s) | APTO |

### Hallazgos

1. OR-Tools 9.15 instala y resuelve en Windows/Python 3.13; no se necesita SciPy MILP ni PuLP.
2. La etapa 1 (minimizar violaciones de variedad) se prueba óptima en menos de 0,4 s.
3. La etapa 2 (minimizar ticket con paquetes) agota sus 3 s y devuelve una solución factible. El contrato de F4.4 ya contempla `feasible` sin prueba de optimalidad; no se debe declarar `optimal`.
4. Ajustar las cotas superiores de `q[p]` al mínimo necesario (sin `+1`) mejora el modelo: etapa 1 de 1,50 s a 0,42 s y etapa 2 de 358,12 € a 334,26 € en la primera medición.
5. Con `num_search_workers=1` y semilla fija, la tanda final dio el mismo ticket (333,18 €) tres veces, pero una tanda anterior varió entre 333,18, 333,42 y 333,52 € porque el límite es de tiempo real. Los tests de optimalidad deben usar instancias pequeñas que terminen antes del límite, no comparar tickets exactos de ejecuciones limitadas por reloj.

### Consecuencias

- Mantener un único solver: OR-Tools CP-SAT.
- F4.3: reutilizar la formulación de demanda, mínimos y variedad y las cotas ajustadas de `q`.
- F4.4: la etapa 2 puede devolver `feasible`; el estado `optimal` solo con prueba.
- F4.9: tests de optimalidad con fuerza bruta en instancia pequeña; tests de rendimiento con margen sobre el límite.
- El spike no persiste catálogo, menús ni precios.

---

## 2026-10-26 — Allowlist de Host y SQLite fuera de OneDrive

### Problema

La app escucha en `127.0.0.1`, pero un navegador puede enviar un `Host` arbitrario
(DNS rebinding). Además, una ruta de datos dentro de OneDrive puede corromper SQLite
por la sincronización de WAL.

### Decisión

- Middleware propio `HostValidationMiddleware`: acepta `127.0.0.1`, `localhost` y
  `::1` (el puerto se ignora) y devuelve `400 INVALID_HOST` con el sobre de error
  homogéneo para el resto.
- `Settings` rechaza `CESTA_DATA_DIR` dentro de OneDrive.
- `run.ps1` resuelve la ruta absoluta, crea el directorio y pasa la variable al
  backend; `scripts/init_db.py` crea el archivo con WAL, `foreign_keys=ON` y
  `busy_timeout=5000`.
- CORS se mantiene solo en desarrollo y solo para `http://localhost:5173`.

### Justificación

- El error homogéneo permite al frontend tratar el fallo como cualquier otro.
- La allowlist sin puerto funciona con Vite, uvicorn y peticiones directas.
- Rechazar OneDrive convierte una recomendación operativa en una garantía.

### Alternativas

- `TrustedHostMiddleware` de Starlette: válido, pero devuelve un 400 de texto plano
  que rompe el contrato de errores.
- Aceptar cualquier `Host` local: no protege frente a DNS rebinding.
- Avisar solo si la base está en OneDrive: se descartó; el riesgo de corrupción es alto.

---

## 2026-10-25 — Informe del spike de catálogo (F0.5)

### Ejecución

- Script: `scripts/spike_catalog.py` (concurrencia 4, sin guardar catálogo).
- Comando: `cd backend; uv run python ..\scripts\spike_catalog.py`.
- Entorno: Windows, Python 3.13.5, OR-Tools 9.15, httpx 0.28, tenacity 9.2.
- CP 22002 / almacén 4389 confirmados.

### Resultado

| Métrica | Valor |
|---|---|
| Secciones | 26 |
| Subcategorías | 152 |
| Subcategorías descargadas | 152 (0 fallidas) |
| Productos vistos (con duplicados) | 4.543 |
| Productos únicos | 4.291 |
| Duplicados entre subcategorías | 252 |
| Precios parseables | 4.291 (100 %) |
| Productos sin precio | 0 |
| Precios no parseables | 0 |
| Productos no publicados | 0 |
| Sin tamaño o formato de paquete | 35 |
| Con peso aproximado (`approx_size`) | 383 |
| Con id de variante no numérico | 65 |
| Tiempo total | 6,37 s |
| Referencia observada | ~4.327 |
| Diferencia | −36 (−0,8 %) |

Umbrales F0.5: **APTO** (≥20 secciones, ≥100 subcategorías, ≥3.000 productos, precios parseables, 0 precios no parseables).

### Hallazgos

1. **`pack_size` puede ser decimal.** El DTO lo tipaba como entero y hacía fallar 67 subcategorías. Ejemplo real: pack de 6 botellas de 1,5 L → `pack_size=1.5`, `total_units=6`, `unit_size=9.0`, `unit_price="1.62"`, `bulk_price="0.18"`. Se cambió a `float | None`; `unit_size` sigue siendo la cantidad total del paquete.
2. **El `id` de producto puede ser texto con sufijo de variante.** Pescado y pan usan ids como `"81649.1"` (peso variable) o `"83203.1"`. El cliente ahora usa `id: str` y `coerce_numbers_to_str`; encaja con `products.external_id` textual de F1.1. Hay 65 ids de este tipo.
3. **Los 403 son transitorios.** Con concurrencia 4 se produjeron 5 `403` en una tanda; al repetir la misma categoría respondió 200. El cliente trata `403`, `429` y `5xx` como reintentables (4 intentos, backoff exponencial desde 1 s). Con eso, la ejecución limpia tiene 0 fallos.
4. **`approx_size=true` identifica peso variable** (383 productos). El MVP debe excluirlos del mapeo ingrediente → producto (F1.3/F2.3), igual que los 35 sin tamaño/formato.
5. **`unit_price` es el precio del paquete**, confirmado con el pack de agua: 1,62 € el pack frente a 0,18 €/L de `bulk_price`. Refuerza la regla de PLAN §12.4 y la normalización de F1.3.
6. **La estructura del catálogo no es plana.** El detalle de subcategoría trae `products` vacío y los productos dentro de `categories[].products`; `all_products()` aplana los grupos.

### Consecuencias

- F1.1: `external_id` debe ser `TEXT` único; no asumir ids numéricos.
- F1.3: convertir `unit_size`/`size_format` a milésimas, tratar `pack_size`/`total_units` como metadatos del pack y descartar `approx_size=true` para el mapeo.
- F1.4: la sync puede alcanzar 152/152 en ~6 s con concurrencia 4; debe reintentar 403/429/5xx y registrar fallos por subcategoría.
- F0.5 no persiste catálogo ni `raw_json`; el informe es reproducible con el script.

---

## 2026-10-25 — Cliente Mercadona asíncrono y fail-closed

### Problema

Había que validar el acceso real a Mercadona antes de diseñar el catálogo persistente, sin acoplar el cliente a un JSON cambiante ni permitir precios de otro almacén.

### Decisión

- `httpx.AsyncClient` con una sesión por cliente; el CP 22002 se fija con `PUT /api/postal-codes/actions/change-pc/` en la primera petición.
- El almacén se valida por la cabecera `x-customer-wh`; si no es `4389`, se lanza `WarehouseUnavailableError` y no se descarga catálogo.
- Se sigue la paginación de `/api/categories/` con `next`; todas las URLs de catálogo llevan `wh=4389` conservando el resto de parámetros.
- Reintentos con tenacity ante errores de transporte, 403, 429 y 5xx (4 intentos, backoff exponencial desde 1 s); otros 4xx no se reintentan.
- DTOs Pydantic con `extra="ignore"` y precios como texto: la normalización a céntimos corresponde a F1.3.
- Fixtures sintéticas en los tests; la API real solo se consulta desde un script manual.

### Justificación

- La concurrencia 4 de F1.4 encaja con un cliente asíncrono.
- Un fallo de almacén debe bloquear la generación de menús, no degradarse con precios de otra zona.
- Ignorar campos desconocidos evita romper el cliente si Mercadona añade metadatos.
- No duplicar la normalización de precios mantiene una única fuente de conversión.

### Alternativas

- Cliente síncrono: suficiente para F0.4 pero obligaría a rehacerlo en F1.4.
- Descargar el catálogo completo en F0.4: fuera de alcance y prohibido en tests.
- Parsear precios en el cliente: duplicaría la lógica de F1.3.
- Reintentar también 4xx: oculta errores de contrato y multiplica llamadas.

---

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
