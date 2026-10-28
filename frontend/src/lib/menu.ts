/** Cliente y tipos del contrato congelado de menús y lista de la compra. */

import { DomainRequestError, requestJson, type ApiErrorBody } from '@/lib/domain';

export type MenuStatus = 'optimal' | 'feasible' | 'relaxed';
export type PriceStatus = 'current' | 'stale';
export type MealSlot = 'lunch' | 'dinner';
export type MenuCourse = 'main' | 'complement';
export type ExclusionScope = 'menu' | 'profile';
export type ExportFormat = 'markdown' | 'csv';

export type MenuSummary = {
  id: number;
  people: number;
  days: number;
  budget_cents: number;
  status: MenuStatus;
  price_status: PriceStatus;
  timed_out: boolean;
  ticket_cents: number;
  consumption_cents: number;
  pantry_consumption_cents: number;
  leftover_value_cents: number;
  revalidated_ticket_cents: number | null;
  previous_ticket_cents: number | null;
  price_delta_cents: number | null;
  revalidated_at: string | null;
  violations: number;
  relaxations: string[];
  postal_code: string;
  warehouse: string;
  prices_captured_at: string | null;
  optimizer_version: string;
  created_at: string;
  updated_at: string;
};

export type MenuSettings = {
  version: number;
  allergen_codes: string[];
  excluded_ingredient_ids: number[];
  excluded_dish_ids: number[];
  excluded_tags: string[];
  pantry: Array<{ ingredient_id: number; quantity_milli: number }>;
  max_repeats: number;
  optimizer_version: string;
};

export type MenuEntryIngredient = {
  ingredient_id: number;
  ingredient_name: string;
  base_unit: 'g' | 'ml' | 'unit';
  used_milli: number;
  consumption_cents: number;
  product_id: number;
};

export type MenuEntry = {
  id: number;
  day_index: number;
  slot: MealSlot;
  course: MenuCourse;
  dish_id: number;
  dish_name: string;
  locked: boolean;
  entry_consumption_cents: number;
  protein_source: string | null;
  tags: string[];
  ingredients: MenuEntryIngredient[];
};

export type MenuDetail = MenuSummary & {
  settings: MenuSettings;
  entries: MenuEntry[];
};

export type MenuPage = {
  items: MenuSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type GenerateStatus = MenuStatus | 'infeasible' | 'timeout';

export type MenuGenerateRequest = {
  people: number;
  days: number;
  budget_cents: number;
  allergen_codes?: string[] | null;
  excluded_ingredient_ids?: number[] | null;
  excluded_dish_ids?: number[] | null;
  excluded_tags?: string[] | null;
  pantry?: Array<{ ingredient_id: number; quantity_milli: number }> | null;
  max_repeats?: number;
};

export type MenuGenerateResponse = {
  status: GenerateStatus;
  is_preview: boolean;
  reason: 'budget' | 'timeout' | null;
  menu_id: number | null;
  people: number;
  days: number;
  budget_cents: number;
  ticket_cents: number | null;
  consumption_cents: number | null;
  pantry_consumption_cents: number | null;
  leftover_value_cents: number | null;
  minimum_ticket_cents: number | null;
  minimum_is_estimate: boolean;
  shortfall_cents: number;
  relaxations: string[];
  suggestions: string[];
  price_status: PriceStatus | null;
  timed_out: boolean;
  postal_code: string;
  warehouse: string;
  prices_captured_at: string | null;
  entries: MenuEntry[];
};

export type ShoppingItem = {
  id: number;
  product_id: number;
  product_name: string;
  brand: string | null;
  ingredient_id: number;
  ingredient_name: string;
  packages: number;
  package_quantity_milli: number;
  package_unit: string;
  package_price_cents: number;
  subtotal_cents: number;
  pantry_quantity_milli: number;
  checked: boolean;
};

export type ShoppingSection = {
  section_id: number | null;
  section_name: string;
  subtotal_cents: number;
  items: ShoppingItem[];
};

export type ShoppingPantryItem = {
  ingredient_id: number;
  ingredient_name: string;
  base_unit: 'g' | 'ml' | 'unit';
  quantity_milli: number;
};

export type ShoppingList = {
  menu_id: number;
  status: MenuStatus;
  price_status: PriceStatus;
  timed_out: boolean;
  people: number;
  days: number;
  budget_cents: number;
  ticket_cents: number;
  consumption_cents: number;
  pantry_consumption_cents: number;
  leftover_value_cents: number;
  revalidated_ticket_cents: number | null;
  previous_ticket_cents: number | null;
  price_delta_cents: number | null;
  revalidated_at: string | null;
  checked_total_cents: number;
  item_count: number;
  checked_count: number;
  cost_per_meal_cents: number;
  cost_per_day_cents: number;
  cost_per_person_day_cents: number;
  postal_code: string;
  warehouse: string;
  prices_captured_at: string | null;
  updated_at: string;
  sections: ShoppingSection[];
  pantry_items: ShoppingPantryItem[];
};

export type ShoppingItemPatch = { checked: boolean } | { already_have: true };

function hasErrorEnvelope(value: unknown): value is { error: NonNullable<ApiErrorBody['error']> } {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as { error?: unknown }).error === 'object'
  );
}

function throwIfErrorEnvelope(value: unknown): void {
  if (hasErrorEnvelope(value)) {
    throw new DomainRequestError(
      value.error.message ?? 'La operación del menú no se pudo completar.',
      value.error.code,
      value.error.details,
    );
  }
}

/** Genera un menú con el perfil y las preferencias actuales. */
export function generateMenu(payload: MenuGenerateRequest): Promise<MenuGenerateResponse> {
  return requestJson<MenuGenerateResponse>('/api/menus/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** Menús guardados, del más reciente al más antiguo. */
export function fetchMenus(params: { limit?: number; offset?: number } = {}): Promise<MenuPage> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 20));
  if (params.offset) search.set('offset', String(params.offset));
  return requestJson<MenuPage>(`/api/menus?${search.toString()}`);
}

/** Detalle de un menú guardado. */
export function fetchMenu(menuId: number): Promise<MenuDetail> {
  return requestJson<MenuDetail>(`/api/menus/${menuId}`);
}

/** Bloquea o desbloquea una entrada del menú. */
export function setEntryLocked(
  menuId: number,
  entryId: number,
  locked: boolean,
): Promise<MenuDetail> {
  return requestJson<MenuDetail>(`/api/menus/${menuId}/entries/${entryId}`, {
    method: 'PATCH',
    body: JSON.stringify({ locked }),
  });
}

/** Cambia el plato de una entrada por otro plato elegible del mismo curso. */
export function swapEntry(menuId: number, entryId: number, dishId: number): Promise<MenuDetail> {
  return requestJson<MenuDetail>(`/api/menus/${menuId}/entries/${entryId}/swap`, {
    method: 'POST',
    body: JSON.stringify({ dish_id: dishId }),
  });
}

/** Añade un acompañamiento al hueco de un plato principal. */
export function addComplement(
  menuId: number,
  mainEntryId: number,
  dishId: number,
): Promise<MenuDetail> {
  return requestJson<MenuDetail>(`/api/menus/${menuId}/entries/${mainEntryId}/complement`, {
    method: 'POST',
    body: JSON.stringify({ dish_id: dishId }),
  });
}

/** Quita el acompañamiento del hueco de un plato principal. */
export function removeComplement(menuId: number, mainEntryId: number): Promise<MenuDetail> {
  return requestJson<MenuDetail>(`/api/menus/${menuId}/entries/${mainEntryId}/complement`, {
    method: 'DELETE',
  });
}

/** Marca el plato de una entrada como «no me gusta» en el menú o en el perfil. */
export function excludeEntry(
  menuId: number,
  entryId: number,
  scope: ExclusionScope,
): Promise<MenuDetail> {
  return requestJson<MenuDetail>(`/api/menus/${menuId}/entries/${entryId}/exclude`, {
    method: 'POST',
    body: JSON.stringify({ scope }),
  });
}

/**
 * Regenera el menú respetando bloqueos y preferencias.
 *
 * El backend puede responder un sobre de error `SOLVER_TIMEOUT` con HTTP 200 y
 * sin persistir nada; se convierte en `DomainRequestError` para la UI.
 */
export async function regenerateMenu(menuId: number): Promise<MenuDetail> {
  const payload = await requestJson<MenuDetail | ApiErrorBody>(`/api/menus/${menuId}/regenerate`, {
    method: 'POST',
  });
  throwIfErrorEnvelope(payload);
  return payload as MenuDetail;
}

/** Revalida precios y ticket sin invalidar el menú guardado. */
export async function revalidateMenu(menuId: number): Promise<MenuDetail> {
  const payload = await requestJson<MenuDetail | ApiErrorBody>(`/api/menus/${menuId}/revalidate`, {
    method: 'POST',
  });
  throwIfErrorEnvelope(payload);
  return payload as MenuDetail;
}

/** Lista de la compra calculada desde el menú persistido. */
export function fetchShoppingList(menuId: number): Promise<ShoppingList> {
  return requestJson<ShoppingList>(`/api/menus/${menuId}/shopping-list`);
}

/** Marca una línea o indica que ya se tiene en casa; devuelve la lista recalculada. */
export function patchShoppingItem(
  menuId: number,
  itemId: number,
  patch: ShoppingItemPatch,
): Promise<ShoppingList> {
  return requestJson<ShoppingList>(`/api/menus/${menuId}/shopping-list/items/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

/** URL de descarga del menú exportado (Markdown o CSV). */
export function menuExportUrl(menuId: number, format: ExportFormat = 'markdown'): string {
  return `/api/menus/${menuId}/export?format=${format}`;
}
