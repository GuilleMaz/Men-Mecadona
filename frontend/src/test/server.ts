import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

import type {
  Exclusion,
  Ingredient,
  PantryItem,
  PantryItemInput,
  Profile,
  ProfileUpdate,
} from '@/lib/domain';

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

const DISH = {
  id: 1,
  slug: 'chicken-rice',
  name: 'Pollo con arroz',
  description: 'Pollo, arroz y cebolla.',
  base_servings: 2,
  meal_types: ['lunch', 'dinner'] as Array<'lunch' | 'dinner'>,
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
  http.get('/api/dishes', () =>
    HttpResponse.json({ items: [DISH], total: 1, limit: 100, offset: 0 }),
  ),
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
);
