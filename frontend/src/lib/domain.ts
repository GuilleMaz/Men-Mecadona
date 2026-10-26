/** Cliente de la API de ingredientes, platos y preferencias. */

export type Allergen = {
  code: string;
  name: string;
};

export type Ingredient = {
  id: number;
  slug: string;
  name: string;
  category: string;
  group: 'vegetable' | 'protein' | 'carb' | 'dairy' | 'fat' | 'fruit' | 'pantry' | 'other';
  base_unit: 'g' | 'ml' | 'unit';
  grams_per_unit: number | null;
  protein_source: string | null;
  serving_group: 'vegetable' | 'protein' | 'carb' | 'none';
  serving_size_milli: number;
  allergens: string[];
  tags: string[];
  active: boolean;
};

export type ProductOption = {
  id: number;
  external_id: string;
  name: string;
  package_quantity_milli: number | null;
  package_unit: string | null;
  package_price_cents: number | null;
  is_default: boolean;
  priority: number;
  allergen_status: string;
  published: boolean;
  eligible: boolean;
};

export type DishIngredient = {
  ingredient: Ingredient;
  quantity_milli: number;
  products: ProductOption[];
};

export type DishSummary = {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  base_servings: number;
  meal_types: Array<'lunch' | 'dinner'>;
  protein_sources: string[];
  has_vegetables: boolean;
  light: boolean;
  carbs: string | null;
  tags: string[];
  allergens: string[];
  eligible: boolean;
  exclusion_reasons: string[];
};

export type DishDetail = DishSummary & {
  ingredients: DishIngredient[];
};

export type DishPage = {
  items: DishSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type IngredientPage = {
  items: Ingredient[];
  total: number;
  limit: number;
  offset: number;
};

export type Profile = {
  id: number;
  people: number;
  days: number;
  budget_cents: number;
  allergen_codes: string[];
};

export type ProfileUpdate = {
  people: number;
  days: number;
  budget_cents: number;
  allergen_codes?: string[];
};

export type Exclusion = {
  id: number;
  kind: 'ingredient' | 'dish' | 'tag';
  ingredient_id: number | null;
  dish_id: number | null;
  tag: string | null;
  label: string;
};

export type ExclusionCreate = {
  ingredient_id?: number;
  dish_id?: number;
  tag?: string;
};

export type PantryItem = {
  id: number;
  ingredient: Ingredient;
  quantity_milli: number;
};

export type PantryItemInput = {
  ingredient_id: number;
  quantity_milli: number;
};

export type PricingPreviewDishInput = {
  dish_id: number;
};

export type PricingPreviewInput = {
  people: number;
  dishes: PricingPreviewDishInput[];
  pantry?: PantryItemInput[];
};

export type PricingProductLine = {
  product_id: number;
  external_id: string;
  name: string;
  package_quantity_milli: number;
  package_unit: string;
  package_price_cents: number;
  packages: number;
  quantity_milli: number;
  subtotal_cents: number;
  used_milli: number;
  leftover_milli: number;
};

export type PricingIngredientCost = {
  ingredient: Ingredient;
  need_milli: number;
  pantry_milli: number;
  pantry_used_milli: number;
  net_need_milli: number;
  purchased_milli: number;
  leftover_milli: number;
  ticket_cents: number;
  consumption_cents: number;
  pantry_consumption_cents: number;
  leftover_value_cents: number;
  products: PricingProductLine[];
};

export type PricingDishCost = {
  index: number;
  dish_id: number;
  dish_name: string;
  servings: number;
  consumption_cents: number;
  per_serving_cents: number;
};

export type PricingPreview = {
  people: number;
  dish_count: number;
  ticket_cents: number;
  consumption_cents: number;
  pantry_consumption_cents: number;
  leftover_value_cents: number;
  dishes: PricingDishCost[];
  ingredients: PricingIngredientCost[];
};

export type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
};

/** Error con el código estable y los detalles que devuelve la API. */
export class DomainRequestError extends Error {
  readonly code: string | undefined;
  readonly details: Record<string, unknown> | undefined;

  constructor(message: string, code?: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'DomainRequestError';
    this.code = code;
    this.details = details;
  }
}

async function readError(response: Response): Promise<DomainRequestError> {
  try {
    const payload = (await response.json()) as ApiErrorBody;
    const message = payload.error?.message ?? `La API respondió con estado ${response.status}`;
    return new DomainRequestError(message, payload.error?.code, payload.error?.details);
  } catch {
    return new DomainRequestError(`La API respondió con estado ${response.status}`);
  }
}

/** Petición JSON con el sobre de errores homogéneo de la API. */
export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    throw await readError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** Lista canónica de alérgenos. */
export function fetchAllergens(): Promise<Allergen[]> {
  return requestJson<Allergen[]>('/api/allergens');
}

/** Ingredientes activos, con búsqueda y grupo. */
export function fetchIngredients(
  params: {
    q?: string;
    group?: Ingredient['group'];
    limit?: number;
    offset?: number;
  } = {},
): Promise<IngredientPage> {
  const search = new URLSearchParams();
  if (params.q) search.set('q', params.q);
  if (params.group) search.set('group', params.group);
  search.set('limit', String(params.limit ?? 200));
  if (params.offset) search.set('offset', String(params.offset));
  return requestJson<IngredientPage>(`/api/ingredients?${search.toString()}`);
}

/** Catálogo de platos con filtros y elegibilidad. */
export function fetchDishes(
  params: {
    q?: string;
    mealType?: 'lunch' | 'dinner';
    tag?: string;
    light?: boolean;
    onlyEligible?: boolean;
    limit?: number;
    offset?: number;
  } = {},
): Promise<DishPage> {
  const search = new URLSearchParams();
  if (params.q) search.set('q', params.q);
  if (params.mealType) search.set('meal_type', params.mealType);
  if (params.tag) search.set('tag', params.tag);
  if (params.light !== undefined) search.set('light', String(params.light));
  if (params.onlyEligible !== undefined) search.set('only_eligible', String(params.onlyEligible));
  search.set('limit', String(params.limit ?? 100));
  if (params.offset) search.set('offset', String(params.offset));
  return requestJson<DishPage>(`/api/dishes?${search.toString()}`);
}

/** Detalle de un plato con composición y productos. */
export function fetchDish(dishId: number): Promise<DishDetail> {
  return requestJson<DishDetail>(`/api/dishes/${dishId}`);
}

/** Perfil local. */
export function fetchProfile(): Promise<Profile> {
  return requestJson<Profile>('/api/profile');
}

/** Actualiza personas, días, presupuesto y alérgenos. */
export function updateProfile(payload: ProfileUpdate): Promise<Profile> {
  return requestJson<Profile>('/api/profile', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

/** Exclusiones del perfil. */
export function fetchExclusions(): Promise<Exclusion[]> {
  return requestJson<Exclusion[]>('/api/exclusions');
}

/** Crea una exclusión. */
export function createExclusion(payload: ExclusionCreate): Promise<Exclusion> {
  return requestJson<Exclusion>('/api/exclusions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** Elimina una exclusión. */
export function deleteExclusion(exclusionId: number): Promise<void> {
  return requestJson<void>(`/api/exclusions/${exclusionId}`, { method: 'DELETE' });
}

/** Despensa actual. */
export function fetchPantry(): Promise<PantryItem[]> {
  return requestJson<PantryItem[]>('/api/pantry');
}

/** Reemplaza la despensa completa. */
export function updatePantry(items: PantryItemInput[]): Promise<PantryItem[]> {
  return requestJson<PantryItem[]>('/api/pantry', {
    method: 'PUT',
    body: JSON.stringify({ items }),
  });
}

/** Preview de coste sin persistir menú ni aplicar filtros de alérgenos. */
export function fetchPricingPreview(payload: PricingPreviewInput): Promise<PricingPreview> {
  return requestJson<PricingPreview>('/api/pricing/preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
