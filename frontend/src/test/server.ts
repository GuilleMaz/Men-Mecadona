import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

import type {
  DishSummary,
  Exclusion,
  Ingredient,
  PantryItem,
  PantryItemInput,
  PricingIngredientCost,
  PricingPreview,
  PricingPreviewInput,
  Profile,
  ProfileUpdate,
} from '@/lib/domain';
import type {
  MenuDetail,
  MenuEntry,
  MenuGenerateResponse,
  MenuSummary,
  ShoppingList,
  ShoppingPantryItem,
  ShoppingSection,
} from '@/lib/menu';

const INGREDIENTS: Ingredient[] = [
  {
    id: 1,
    slug: 'rice',
    name: 'Arroz',
    category: 'grains',
    group: 'carb',
    base_unit: 'g',
    grams_per_unit: null,
    protein_source: null,
    serving_group: 'carb',
    serving_size_milli: 60000,
    allergens: [],
    tags: ['carb_type:rice'],
    active: true,
  },
  {
    id: 2,
    slug: 'onion',
    name: 'Cebolla',
    category: 'vegetables',
    group: 'vegetable',
    base_unit: 'g',
    grams_per_unit: null,
    protein_source: null,
    serving_group: 'vegetable',
    serving_size_milli: 150000,
    allergens: [],
    tags: [],
    active: true,
  },
  {
    id: 3,
    slug: 'chicken',
    name: 'Pollo',
    category: 'meat',
    group: 'protein',
    base_unit: 'g',
    grams_per_unit: null,
    protein_source: 'chicken',
    serving_group: 'protein',
    serving_size_milli: 100000,
    allergens: [],
    tags: [],
    active: true,
  },
];

const DISH: DishSummary = {
  id: 1,
  slug: 'chicken-rice',
  name: 'Pollo con arroz',
  description: 'Pollo, arroz y cebolla.',
  base_servings: 2,
  meal_types: ['lunch', 'dinner'],
  protein_sources: ['chicken'],
  has_vegetables: true,
  light: false,
  carbs: 'rice',
  tags: ['rice'],
  allergens: [],
  eligible: true,
  exclusion_reasons: [],
};

const DISH_DETAIL = {
  ...DISH,
  ingredients: [
    {
      ingredient: INGREDIENTS[2]!,
      quantity_milli: 300000,
      products: [
        {
          id: 10,
          external_id: '1002',
          name: 'Pollo',
          package_quantity_milli: 500000,
          package_unit: 'g',
          package_price_cents: 450,
          is_default: true,
          priority: 1,
          allergen_status: 'known',
          published: true,
          eligible: true,
        },
      ],
    },
    {
      ingredient: INGREDIENTS[0]!,
      quantity_milli: 160000,
      products: [
        {
          id: 11,
          external_id: '1001',
          name: 'Arroz',
          package_quantity_milli: 1000000,
          package_unit: 'g',
          package_price_cents: 115,
          is_default: true,
          priority: 1,
          allergen_status: 'known',
          published: true,
          eligible: true,
        },
      ],
    },
    {
      ingredient: INGREDIENTS[1]!,
      quantity_milli: 100000,
      products: [],
    },
  ],
};

const SWAP_DISHES: DishSummary[] = [
  DISH,
  {
    id: 2,
    slug: 'potato-omelette',
    name: 'Tortilla de patatas',
    description: 'Huevo y patata.',
    base_servings: 2,
    meal_types: ['dinner'],
    protein_sources: ['eggs'],
    has_vegetables: false,
    light: false,
    carbs: 'potato',
    tags: ['vegetarian'],
    allergens: ['eggs'],
    eligible: true,
    exclusion_reasons: [],
  },
  {
    id: 3,
    slug: 'lentil-stew',
    name: 'Lentejas guisadas',
    description: 'Lentejas con verduras.',
    base_servings: 2,
    meal_types: ['lunch'],
    protein_sources: ['legumes'],
    has_vegetables: true,
    light: false,
    carbs: 'legume',
    tags: ['legume', 'stew'],
    allergens: [],
    eligible: true,
    exclusion_reasons: [],
  },
  {
    id: 4,
    slug: 'vegetable-soup',
    name: 'Sopa de verduras',
    description: 'Calabacín y cebolla.',
    base_servings: 2,
    meal_types: ['dinner'],
    protein_sources: [],
    has_vegetables: true,
    light: true,
    carbs: null,
    tags: ['soup', 'vegetarian'],
    allergens: [],
    eligible: true,
    exclusion_reasons: [],
  },
  {
    id: 5,
    slug: 'sirloin',
    name: 'Solomillo con patatas',
    description: 'Solomillo y patatas.',
    base_servings: 2,
    meal_types: ['dinner'],
    protein_sources: ['beef'],
    has_vegetables: false,
    light: false,
    carbs: 'potato',
    tags: ['red_meat'],
    allergens: [],
    eligible: true,
    exclusion_reasons: [],
  },
  {
    id: 6,
    slug: 'pasta-salad',
    name: 'Ensalada de pasta',
    description: 'Pasta, tomate y atún.',
    base_servings: 2,
    meal_types: ['lunch'],
    protein_sources: ['tuna'],
    has_vegetables: true,
    light: true,
    carbs: 'pasta',
    tags: ['salad', 'fish'],
    allergens: ['fish'],
    eligible: true,
    exclusion_reasons: [],
  },
];

const DISH_ENTRY_CENTS: Record<number, number> = {
  1: 136,
  2: 128,
  3: 130,
  4: 120,
  5: 12_000,
  6: 110,
};

const ALLERGENS = [
  ['gluten', 'Gluten'],
  ['crustaceans', 'Crustáceos'],
  ['eggs', 'Huevo'],
  ['fish', 'Pescado'],
  ['peanuts', 'Cacahuetes'],
  ['soybeans', 'Soja'],
  ['milk', 'Leche'],
  ['nuts', 'Frutos de cáscara'],
  ['celery', 'Apio'],
  ['mustard', 'Mostaza'],
  ['sesame', 'Sésamo'],
  ['sulphites', 'Sulfitos'],
  ['lupin', 'Altramuces'],
  ['molluscs', 'Moluscos'],
  ['unknown', 'Sin confirmar'],
].map(([code, name]) => ({ code: code!, name: name! }));

const DEFAULT_PROFILE: Profile = {
  id: 1,
  people: 2,
  days: 7,
  budget_cents: 7000,
  allergen_codes: [],
};

function exclusionFromBody(body: Record<string, unknown>): Exclusion {
  if (typeof body.dish_id === 'number') {
    return {
      id: 1,
      kind: 'dish',
      ingredient_id: null,
      dish_id: body.dish_id,
      tag: null,
      label: DISH.name,
    };
  }
  if (typeof body.ingredient_id === 'number') {
    const ingredient = INGREDIENTS.find((item) => item.id === body.ingredient_id);
    return {
      id: 1,
      kind: 'ingredient',
      ingredient_id: body.ingredient_id,
      dish_id: null,
      tag: null,
      label: ingredient?.name ?? 'Ingrediente',
    };
  }
  return {
    id: 1,
    kind: 'tag',
    ingredient_id: null,
    dish_id: null,
    tag: String(body.tag ?? ''),
    label: String(body.tag ?? ''),
  };
}

const PRICING_INGREDIENTS: PricingIngredientCost[] = [
  {
    ingredient: INGREDIENTS[2]!,
    need_milli: 300000,
    pantry_milli: 0,
    pantry_used_milli: 0,
    net_need_milli: 300000,
    purchased_milli: 500000,
    leftover_milli: 200000,
    ticket_cents: 450,
    consumption_cents: 270,
    pantry_consumption_cents: 0,
    leftover_value_cents: 180,
    products: [
      {
        product_id: 10,
        external_id: '1002',
        name: 'Pollo',
        package_quantity_milli: 500000,
        package_unit: 'g',
        package_price_cents: 450,
        packages: 1,
        quantity_milli: 500000,
        subtotal_cents: 450,
        used_milli: 300000,
        leftover_milli: 200000,
      },
    ],
  },
  {
    ingredient: INGREDIENTS[0]!,
    need_milli: 160000,
    pantry_milli: 0,
    pantry_used_milli: 0,
    net_need_milli: 160000,
    purchased_milli: 1000000,
    leftover_milli: 840000,
    ticket_cents: 115,
    consumption_cents: 18,
    pantry_consumption_cents: 0,
    leftover_value_cents: 97,
    products: [
      {
        product_id: 11,
        external_id: '1001',
        name: 'Arroz',
        package_quantity_milli: 1000000,
        package_unit: 'g',
        package_price_cents: 115,
        packages: 1,
        quantity_milli: 1000000,
        subtotal_cents: 115,
        used_milli: 160000,
        leftover_milli: 840000,
      },
    ],
  },
  {
    ingredient: INGREDIENTS[1]!,
    need_milli: 100000,
    pantry_milli: 0,
    pantry_used_milli: 0,
    net_need_milli: 100000,
    purchased_milli: 0,
    leftover_milli: 0,
    ticket_cents: 0,
    consumption_cents: 0,
    pantry_consumption_cents: 0,
    leftover_value_cents: 0,
    products: [],
  },
];

function pricingPreviewFor(body: PricingPreviewInput): PricingPreview {
  const people = body.people;
  const perServing = 144;
  const consumption = perServing * people;
  const ticket = 565 + Math.max(0, people - 2) * perServing;
  return {
    people,
    dish_count: body.dishes.length,
    ticket_cents: ticket,
    consumption_cents: consumption,
    pantry_consumption_cents: 0,
    leftover_value_cents: Math.max(0, ticket - consumption),
    dishes: body.dishes.map((entry, index) => ({
      index,
      dish_id: entry.dish_id,
      dish_name: DISH.name,
      servings: people,
      consumption_cents: consumption,
      per_serving_cents: perServing,
    })),
    ingredients: PRICING_INGREDIENTS,
  };
}

// ---------------------------------------------------------------------------
// Fixtures deterministas de menú y lista de la compra (F4.7/F4.8)
// ---------------------------------------------------------------------------

const MENU_ENTRY_TEMPLATES: MenuEntry[] = [
  {
    id: 1,
    day_index: 0,
    slot: 'lunch',
    dish_id: 1,
    dish_name: 'Pollo con arroz',
    locked: false,
    entry_consumption_cents: 136,
    protein_source: 'chicken',
    tags: ['rice'],
    ingredients: [
      {
        ingredient_id: 3,
        ingredient_name: 'Pollo',
        base_unit: 'g',
        used_milli: 150000,
        consumption_cents: 80,
        product_id: 10,
      },
      {
        ingredient_id: 1,
        ingredient_name: 'Arroz',
        base_unit: 'g',
        used_milli: 80000,
        consumption_cents: 56,
        product_id: 11,
      },
    ],
  },
  {
    id: 2,
    day_index: 0,
    slot: 'dinner',
    dish_id: 2,
    dish_name: 'Tortilla de patatas',
    locked: false,
    entry_consumption_cents: 136,
    protein_source: 'eggs',
    tags: ['vegetarian'],
    ingredients: [
      {
        ingredient_id: 4,
        ingredient_name: 'Huevo',
        base_unit: 'unit',
        used_milli: 4000,
        consumption_cents: 70,
        product_id: 12,
      },
      {
        ingredient_id: 5,
        ingredient_name: 'Patata',
        base_unit: 'g',
        used_milli: 300000,
        consumption_cents: 66,
        product_id: 13,
      },
    ],
  },
  {
    id: 3,
    day_index: 1,
    slot: 'lunch',
    dish_id: 3,
    dish_name: 'Lentejas guisadas',
    locked: false,
    entry_consumption_cents: 136,
    protein_source: 'legumes',
    tags: ['legume', 'stew'],
    ingredients: [
      {
        ingredient_id: 6,
        ingredient_name: 'Lentejas',
        base_unit: 'g',
        used_milli: 250000,
        consumption_cents: 90,
        product_id: 14,
      },
      {
        ingredient_id: 7,
        ingredient_name: 'Zanahoria',
        base_unit: 'g',
        used_milli: 120000,
        consumption_cents: 46,
        product_id: 15,
      },
    ],
  },
  {
    id: 4,
    day_index: 1,
    slot: 'dinner',
    dish_id: 4,
    dish_name: 'Sopa de verduras',
    locked: false,
    entry_consumption_cents: 136,
    protein_source: null,
    tags: ['soup', 'vegetarian'],
    ingredients: [
      {
        ingredient_id: 8,
        ingredient_name: 'Calabacín',
        base_unit: 'g',
        used_milli: 250000,
        consumption_cents: 70,
        product_id: 16,
      },
      {
        ingredient_id: 2,
        ingredient_name: 'Cebolla',
        base_unit: 'g',
        used_milli: 150000,
        consumption_cents: 66,
        product_id: 17,
      },
    ],
  },
];

const BASE_MENU: MenuDetail = {
  id: 1,
  people: 2,
  days: 2,
  budget_cents: 7000,
  status: 'feasible',
  price_status: 'current',
  timed_out: false,
  ticket_cents: 545,
  consumption_cents: 544,
  pantry_consumption_cents: 20,
  leftover_value_cents: 21,
  revalidated_ticket_cents: null,
  violations: 0,
  relaxations: [],
  postal_code: '22002',
  warehouse: '4389',
  prices_captured_at: '2026-10-26T08:00:00Z',
  optimizer_version: '1',
  created_at: '2026-10-26T09:00:00Z',
  updated_at: '2026-10-26T09:00:00Z',
  settings: {
    version: 1,
    allergen_codes: [],
    excluded_ingredient_ids: [],
    excluded_dish_ids: [],
    excluded_tags: [],
    pantry: [{ ingredient_id: 2, quantity_milli: 200000 }],
    max_repeats: 1,
    optimizer_version: '1',
  },
  entries: MENU_ENTRY_TEMPLATES,
};

const BASE_SHOPPING_SECTIONS: ShoppingSection[] = [
  {
    section_id: 1,
    section_name: 'Carnicería',
    subtotal_cents: 450,
    items: [
      {
        id: 1,
        product_id: 10,
        product_name: 'Pollo',
        brand: 'Mercadona',
        ingredient_id: 3,
        ingredient_name: 'Pollo',
        packages: 1,
        package_quantity_milli: 500000,
        package_unit: 'g',
        package_price_cents: 450,
        subtotal_cents: 450,
        pantry_quantity_milli: 0,
        checked: false,
      },
    ],
  },
  {
    section_id: 2,
    section_name: 'Arroz y pasta',
    subtotal_cents: 95,
    items: [
      {
        id: 2,
        product_id: 11,
        product_name: 'Arroz redondo',
        brand: 'Hacendado',
        ingredient_id: 1,
        ingredient_name: 'Arroz',
        packages: 1,
        package_quantity_milli: 1000000,
        package_unit: 'g',
        package_price_cents: 95,
        subtotal_cents: 95,
        pantry_quantity_milli: 0,
        checked: false,
      },
    ],
  },
];

const BASE_PANTRY_ITEMS: ShoppingPantryItem[] = [
  { ingredient_id: 2, ingredient_name: 'Cebolla', base_unit: 'g', quantity_milli: 200000 },
];

type MenuFixtureState = {
  detail: MenuDetail;
  sections: ShoppingSection[];
  pantryItems: ShoppingPantryItem[];
};

function createMenuFixtureState(): MenuFixtureState {
  return {
    detail: structuredClone(BASE_MENU),
    sections: structuredClone(BASE_SHOPPING_SECTIONS),
    pantryItems: structuredClone(BASE_PANTRY_ITEMS),
  };
}

let menuState: MenuFixtureState = createMenuFixtureState();

/** Menú sintético inicial, para que los tests puedan partir de él. */
export const SAMPLE_MENU: MenuDetail = BASE_MENU;

/** Lista de la compra sintética inicial. */
export const SAMPLE_SHOPPING_LIST: ShoppingList = buildShoppingList();

/** Restablece los datos sintéticos de menú entre tests. */
export function resetMenuFixture(): void {
  menuState = createMenuFixtureState();
}

function nowIso(): string {
  return '2026-10-26T10:00:00Z';
}

function apiError(
  code: string,
  message: string,
  status: number,
  details: Record<string, unknown> = {},
) {
  return HttpResponse.json({ error: { code, message, details } }, { status });
}

function menuNotFound() {
  return apiError('NOT_FOUND', 'El menú no existe.', 404);
}

function summaryOf(detail: MenuDetail): MenuSummary {
  return {
    id: detail.id,
    people: detail.people,
    days: detail.days,
    budget_cents: detail.budget_cents,
    status: detail.status,
    price_status: detail.price_status,
    timed_out: detail.timed_out,
    ticket_cents: detail.ticket_cents,
    consumption_cents: detail.consumption_cents,
    pantry_consumption_cents: detail.pantry_consumption_cents,
    leftover_value_cents: detail.leftover_value_cents,
    revalidated_ticket_cents: detail.revalidated_ticket_cents,
    violations: detail.violations,
    relaxations: detail.relaxations,
    postal_code: detail.postal_code,
    warehouse: detail.warehouse,
    prices_captured_at: detail.prices_captured_at,
    optimizer_version: detail.optimizer_version,
    created_at: detail.created_at,
    updated_at: detail.updated_at,
  };
}

function generateResponse(detail: MenuDetail): MenuGenerateResponse {
  return {
    status: detail.status,
    is_preview: false,
    reason: null,
    menu_id: detail.id,
    people: detail.people,
    days: detail.days,
    budget_cents: detail.budget_cents,
    ticket_cents: detail.ticket_cents,
    consumption_cents: detail.consumption_cents,
    pantry_consumption_cents: detail.pantry_consumption_cents,
    leftover_value_cents: detail.leftover_value_cents,
    minimum_ticket_cents: null,
    minimum_is_estimate: false,
    shortfall_cents: 0,
    relaxations: detail.relaxations,
    suggestions: [],
    price_status: detail.price_status,
    timed_out: detail.timed_out,
    postal_code: detail.postal_code,
    warehouse: detail.warehouse,
    prices_captured_at: detail.prices_captured_at,
    entries: detail.entries,
  };
}

function entriesForDays(days: number): MenuEntry[] {
  const lunches = MENU_ENTRY_TEMPLATES.filter((entry) => entry.slot === 'lunch');
  const dinners = MENU_ENTRY_TEMPLATES.filter((entry) => entry.slot === 'dinner');
  return Array.from({ length: days * 2 }, (_, index) => {
    const slot = index % 2 === 0 ? 'lunch' : 'dinner';
    const pool = slot === 'lunch' ? lunches : dinners;
    const template = pool[Math.floor(index / 4) % pool.length]!;
    return {
      ...structuredClone(template),
      id: index + 1,
      day_index: Math.floor(index / 2),
      slot,
      locked: false,
    };
  });
}

function swapDishInEntry(entry: MenuEntry, dish: DishSummary): number {
  const previous = entry.entry_consumption_cents;
  const next = DISH_ENTRY_CENTS[dish.id] ?? 136;
  entry.dish_id = dish.id;
  entry.dish_name = dish.name;
  entry.entry_consumption_cents = next;
  entry.protein_source = dish.protein_sources[0] ?? null;
  entry.tags = [...dish.tags];
  entry.ingredients = [];
  return next - previous;
}

function recalcSectionSubtotals(): void {
  for (const section of menuState.sections) {
    section.subtotal_cents = section.items.reduce((sum, item) => sum + item.subtotal_cents, 0);
  }
}

function buildShoppingList(): ShoppingList {
  recalcSectionSubtotals();
  const detail = menuState.detail;
  const sections = structuredClone(menuState.sections);
  const items = sections.flatMap((section) => section.items);
  const ticket = sections.reduce((sum, section) => sum + section.subtotal_cents, 0);
  const checkedItems = items.filter((item) => item.checked);

  return {
    menu_id: detail.id,
    status: detail.status,
    price_status: detail.price_status,
    timed_out: detail.timed_out,
    people: detail.people,
    days: detail.days,
    budget_cents: detail.budget_cents,
    ticket_cents: ticket,
    consumption_cents: detail.consumption_cents,
    pantry_consumption_cents: detail.pantry_consumption_cents,
    leftover_value_cents: detail.leftover_value_cents,
    checked_total_cents: checkedItems.reduce((sum, item) => sum + item.subtotal_cents, 0),
    item_count: items.length,
    checked_count: checkedItems.length,
    cost_per_meal_cents: Math.round(ticket / (detail.days * 2)),
    cost_per_day_cents: Math.round(ticket / detail.days),
    cost_per_person_day_cents: Math.round(ticket / (detail.days * detail.people)),
    postal_code: detail.postal_code,
    warehouse: detail.warehouse,
    prices_captured_at: detail.prices_captured_at,
    updated_at: detail.updated_at,
    sections,
    pantry_items: structuredClone(menuState.pantryItems),
  };
}

/**
 * Servidor MSW para los tests. Los handlers por defecto permiten montar el
 * layout completo sin red real; cada test puede sobrescribirlos con `server.use`.
 */
export const server = setupServer(
  http.get('/api/health', () => HttpResponse.json({ status: 'ok' })),
  http.get('/api/catalog/status', () =>
    HttpResponse.json({
      schema_ready: true,
      is_syncing: false,
      product_count: 0,
      category_count: 0,
      food_category_count: 0,
      last_sync: null,
      last_success_at: null,
      prices_captured_at: null,
      postal_code: '22002',
      warehouse: null,
    }),
  ),
  http.post('/api/catalog/sync', () =>
    HttpResponse.json({ sync_run_id: 1, status: 'running' }, { status: 202 }),
  ),
  http.get('/api/allergens', () => HttpResponse.json(ALLERGENS)),
  http.get('/api/ingredients', () =>
    HttpResponse.json({ items: INGREDIENTS, total: INGREDIENTS.length, limit: 200, offset: 0 }),
  ),
  http.get('/api/dishes', ({ request }) => {
    const mealType = new URL(request.url).searchParams.get('meal_type');
    if (mealType === 'lunch' || mealType === 'dinner') {
      const items = SWAP_DISHES.filter((dish) => dish.meal_types.includes(mealType));
      return HttpResponse.json({ items, total: items.length, limit: 100, offset: 0 });
    }
    return HttpResponse.json({ items: [DISH], total: 1, limit: 100, offset: 0 });
  }),
  http.get('/api/dishes/:dishId', () => HttpResponse.json(DISH_DETAIL)),
  http.get('/api/profile', () => HttpResponse.json(DEFAULT_PROFILE)),
  http.put('/api/profile', async ({ request }) => {
    const body = (await request.json()) as ProfileUpdate;
    return HttpResponse.json({ id: 1, ...body });
  }),
  http.get('/api/exclusions', () => HttpResponse.json([])),
  http.post('/api/exclusions', async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json(exclusionFromBody(body), { status: 201 });
  }),
  http.delete('/api/exclusions/:exclusionId', () => new HttpResponse(null, { status: 204 })),
  http.get('/api/pantry', () => HttpResponse.json([])),
  http.put('/api/pantry', async ({ request }) => {
    const body = (await request.json()) as { items?: PantryItemInput[] };
    const items: PantryItem[] = (body.items ?? []).map((item, index) => {
      const ingredient = INGREDIENTS.find((candidate) => candidate.id === item.ingredient_id);
      return {
        id: index + 1,
        ingredient: ingredient ?? INGREDIENTS[0]!,
        quantity_milli: item.quantity_milli,
      };
    });
    return HttpResponse.json(items);
  }),
  http.post('/api/pricing/preview', async ({ request }) => {
    const body = (await request.json()) as PricingPreviewInput;
    return HttpResponse.json(pricingPreviewFor(body));
  }),

  // Menús (F4.7)
  http.post('/api/menus/generate', async ({ request }) => {
    const body = (await request.json()) as {
      people: number;
      days: number;
      budget_cents: number;
    };
    const entries = entriesForDays(body.days);
    const consumption = entries.reduce((sum, entry) => sum + entry.entry_consumption_cents, 0);
    const ticket = Math.min(body.budget_cents, consumption + 1);
    menuState.detail = {
      ...menuState.detail,
      people: body.people,
      days: body.days,
      budget_cents: body.budget_cents,
      ticket_cents: ticket,
      consumption_cents: consumption,
      leftover_value_cents: Math.max(
        0,
        ticket + menuState.detail.pantry_consumption_cents - consumption,
      ),
      entries,
      updated_at: nowIso(),
    };
    return HttpResponse.json(generateResponse(menuState.detail));
  }),
  http.get('/api/menus', () =>
    HttpResponse.json({
      items: [summaryOf(menuState.detail)],
      total: 1,
      limit: 20,
      offset: 0,
    }),
  ),
  http.get('/api/menus/:menuId', ({ params }) => {
    if (Number(params.menuId) !== menuState.detail.id) return menuNotFound();
    return HttpResponse.json(structuredClone(menuState.detail));
  }),
  http.patch('/api/menus/:menuId/entries/:entryId', async ({ params, request }) => {
    if (Number(params.menuId) !== menuState.detail.id) return menuNotFound();
    const body = (await request.json()) as { locked?: boolean };
    const entry = menuState.detail.entries.find((item) => item.id === Number(params.entryId));
    if (!entry) return apiError('NOT_FOUND', 'La entrada no existe.', 404);
    entry.locked = Boolean(body.locked);
    menuState.detail.updated_at = nowIso();
    return HttpResponse.json(structuredClone(menuState.detail));
  }),
  http.post('/api/menus/:menuId/entries/:entryId/swap', async ({ params, request }) => {
    if (Number(params.menuId) !== menuState.detail.id) return menuNotFound();
    const body = (await request.json()) as { dish_id?: number };
    const entry = menuState.detail.entries.find((item) => item.id === Number(params.entryId));
    if (!entry) return apiError('NOT_FOUND', 'La entrada no existe.', 404);
    const dish = SWAP_DISHES.find((candidate) => candidate.id === body.dish_id);
    if (!dish) return apiError('NOT_FOUND', 'El plato no existe.', 404);

    const nextCost = DISH_ENTRY_CENTS[dish.id] ?? 136;
    const nextTicket = menuState.detail.ticket_cents - entry.entry_consumption_cents + nextCost;
    if (nextTicket > menuState.detail.budget_cents) {
      return apiError(
        'BUDGET_EXCEEDED',
        'El cambio supera el presupuesto y no se ha aplicado.',
        422,
        { reason: 'budget' },
      );
    }

    const delta = swapDishInEntry(entry, dish);
    menuState.detail.ticket_cents += delta;
    menuState.detail.consumption_cents += delta;
    menuState.detail.updated_at = nowIso();
    return HttpResponse.json(structuredClone(menuState.detail));
  }),
  http.post('/api/menus/:menuId/entries/:entryId/exclude', async ({ params, request }) => {
    if (Number(params.menuId) !== menuState.detail.id) return menuNotFound();
    const body = (await request.json()) as { scope?: 'menu' | 'profile' };
    if (body.scope !== 'menu' && body.scope !== 'profile') {
      return apiError('VALIDATION_ERROR', 'El alcance no es válido.', 422);
    }
    const entry = menuState.detail.entries.find((item) => item.id === Number(params.entryId));
    if (!entry) return apiError('NOT_FOUND', 'La entrada no existe.', 404);

    const replacement = SWAP_DISHES.find(
      (dish) =>
        dish.id !== entry.dish_id &&
        dish.id !== 5 &&
        dish.meal_types.includes(entry.slot) &&
        dish.eligible,
    );
    if (!replacement) {
      return apiError('NO_FEASIBLE_MENU', 'No hay otro plato elegible para este hueco.', 422, {
        reason: 'no_assignment',
      });
    }
    const delta = swapDishInEntry(entry, replacement);
    menuState.detail.ticket_cents += delta;
    menuState.detail.consumption_cents += delta;
    menuState.detail.updated_at = nowIso();
    return HttpResponse.json(structuredClone(menuState.detail));
  }),
  http.post('/api/menus/:menuId/regenerate', ({ params }) => {
    if (Number(params.menuId) !== menuState.detail.id) return menuNotFound();
    let delta = 0;
    for (const entry of menuState.detail.entries) {
      if (entry.locked) continue;
      const candidates = SWAP_DISHES.filter(
        (dish) =>
          dish.id !== entry.dish_id && dish.id !== 5 && dish.meal_types.includes(entry.slot),
      );
      const replacement = candidates[entry.day_index % candidates.length];
      if (replacement) delta += swapDishInEntry(entry, replacement);
    }
    if (menuState.detail.ticket_cents + delta > menuState.detail.budget_cents) {
      return apiError('BUDGET_EXCEEDED', 'El nuevo menú no cabe en el presupuesto.', 422, {
        reason: 'budget',
      });
    }
    menuState.detail.ticket_cents += delta;
    menuState.detail.consumption_cents += delta;
    menuState.detail.updated_at = nowIso();
    return HttpResponse.json(structuredClone(menuState.detail));
  }),
  http.post('/api/menus/:menuId/revalidate', ({ params }) => {
    if (Number(params.menuId) !== menuState.detail.id) return menuNotFound();
    menuState.detail.price_status = 'current';
    menuState.detail.revalidated_ticket_cents = null;
    menuState.detail.updated_at = nowIso();
    return HttpResponse.json(structuredClone(menuState.detail));
  }),

  // Lista de la compra (F4.8)
  http.get('/api/menus/:menuId/shopping-list', ({ params }) => {
    if (Number(params.menuId) !== menuState.detail.id) return menuNotFound();
    return HttpResponse.json(buildShoppingList());
  }),
  http.patch('/api/menus/:menuId/shopping-list/items/:itemId', async ({ params, request }) => {
    if (Number(params.menuId) !== menuState.detail.id) return menuNotFound();
    const body = (await request.json()) as { checked?: boolean; already_have?: true };
    const hasChecked = typeof body.checked === 'boolean';
    const hasAlreadyHave = body.already_have === true;
    if (hasChecked === hasAlreadyHave) {
      return apiError('VALIDATION_ERROR', 'Envía exactamente uno de checked o already_have.', 422);
    }

    const itemId = Number(params.itemId);
    const section = menuState.sections.find((candidate) =>
      candidate.items.some((item) => item.id === itemId),
    );
    const item = section?.items.find((candidate) => candidate.id === itemId);
    if (!section || !item) {
      return apiError('NOT_FOUND', 'La línea no pertenece al menú.', 404);
    }

    if (hasChecked) {
      item.checked = body.checked!;
    } else {
      section.items = section.items.filter((candidate) => candidate.id !== itemId);
      menuState.detail.ticket_cents -= item.subtotal_cents;
      menuState.detail.pantry_consumption_cents += item.subtotal_cents;
      const baseUnit =
        item.package_unit === 'ml' ? 'ml' : item.package_unit === 'unit' ? 'unit' : 'g';
      const existing = menuState.pantryItems.find(
        (pantryItem) => pantryItem.ingredient_id === item.ingredient_id,
      );
      const snapshot = menuState.detail.settings.pantry.find(
        (pantryItem) => pantryItem.ingredient_id === item.ingredient_id,
      );
      const addedMilli = item.packages * item.package_quantity_milli;
      if (existing) {
        existing.quantity_milli += addedMilli;
      } else {
        menuState.pantryItems.push({
          ingredient_id: item.ingredient_id,
          ingredient_name: item.ingredient_name,
          base_unit: baseUnit,
          quantity_milli: addedMilli,
        });
      }
      if (snapshot) {
        snapshot.quantity_milli += addedMilli;
      } else {
        menuState.detail.settings.pantry.push({
          ingredient_id: item.ingredient_id,
          quantity_milli: addedMilli,
        });
      }
    }

    menuState.detail.updated_at = nowIso();
    return HttpResponse.json(buildShoppingList());
  }),

  // Exportación
  http.get('/api/menus/:menuId/export', ({ params, request }) => {
    if (Number(params.menuId) !== menuState.detail.id) return menuNotFound();
    const format = new URL(request.url).searchParams.get('format') ?? 'markdown';
    if (format === 'csv') {
      return new HttpResponse(
        'seccion,producto,ingrediente,paquetes,cantidad_paquete,unidad,precio_paquete_cents,subtotal_cents,marcado\n',
        {
          headers: {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': `attachment; filename="menu-${menuState.detail.id}.csv"`,
          },
        },
      );
    }
    if (format !== 'markdown') {
      return apiError('VALIDATION_ERROR', 'El formato no es válido.', 422);
    }
    return new HttpResponse('# Menú de prueba\n\nSin recetas ni pasos de cocina.\n', {
      headers: {
        'Content-Type': 'text/markdown; charset=utf-8',
        'Content-Disposition': `attachment; filename="menu-${menuState.detail.id}.md"`,
      },
    });
  }),
);
