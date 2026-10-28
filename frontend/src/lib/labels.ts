/** Etiquetas y formatos compartidos por las pantallas de platos y ajustes. */

export const TAG_LABELS: Record<string, string> = {
  fish: 'Pescado',
  seafood: 'Marisco',
  legume: 'Legumbre',
  red_meat: 'Carne roja',
  vegetarian: 'Vegetariano',
  vegan: 'Vegano',
  soup: 'Sopa',
  salad: 'Ensalada',
  pasta: 'Pasta',
  rice: 'Arroz',
  stew: 'Guiso',
  spicy: 'Picante',
  sandwich: 'Bocadillo',
  dessert: 'Postre',
};

export const MEAL_LABELS: Record<string, string> = {
  lunch: 'Comida',
  dinner: 'Cena',
};

export const COURSE_LABELS: Record<string, string> = {
  main: 'Principal',
  complement: 'Acompañamiento',
};

export const ROLE_LABELS: Record<string, string> = {
  main: 'Principal',
  complement: 'Acompañamiento',
};

export const MENU_STATUS_LABELS: Record<string, string> = {
  optimal: 'Óptimo',
  feasible: 'Factible',
  relaxed: 'Relajado',
};

export const PRICE_STATUS_LABELS: Record<string, string> = {
  current: 'Precios actuales',
  stale: 'Precios desactualizados',
};

export const PROTEIN_LABELS: Record<string, string> = {
  chicken: 'Pollo',
  turkey: 'Pavo',
  beef: 'Ternera',
  pork: 'Cerdo',
  fish: 'Pescado',
  tuna: 'Atún',
  salmon: 'Salmón',
  eggs: 'Huevo',
  egg: 'Huevo',
  legumes: 'Legumbre',
  legume: 'Legumbre',
  tofu: 'Tofu',
  cheese: 'Queso',
  seafood: 'Marisco',
  lamb: 'Cordero',
  rabbit: 'Conejo',
};

export const RELAXATION_LABELS: Record<string, string> = {
  protein_sources: 'Falta variedad de proteínas',
  fish: 'Menos pescado del recomendado',
  legumes: 'Menos legumbres de las recomendadas',
  red_meat: 'Más carne roja de la recomendada',
  light_dinners: 'Cenas menos ligeras de lo recomendado',
  carb_sources: 'Falta variedad de hidratos',
  legume_dominance: 'Demasiados platos principales de legumbre',
  protein_balance: 'Reparto de proteínas poco equilibrado',
  same_day_protein: 'Misma proteína en comida y cena',
};

export const EXCLUSION_REASON_LABELS: Record<string, string> = {
  dish_excluded: 'plato excluido',
  tag_excluded: 'etiqueta excluida',
  ingredient_excluded: 'ingrediente excluido',
  ingredient_allergen: 'alérgeno declarado',
  no_eligible_product: 'sin producto elegible',
};

const numberFormatter = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 });

export const euroFormatter = new Intl.NumberFormat('es-ES', {
  style: 'currency',
  currency: 'EUR',
});

export function tagLabel(tag: string): string {
  return TAG_LABELS[tag] ?? tag;
}

export function mealLabel(meal: string): string {
  return MEAL_LABELS[meal] ?? meal;
}

export function proteinLabel(protein: string): string {
  return PROTEIN_LABELS[protein] ?? protein;
}

/** Importe en céntimos formateado como euros. */
export function formatEuro(cents: number): string {
  return euroFormatter.format(cents / 100);
}

const dateTimeFormatter = new Intl.DateTimeFormat('es-ES', {
  dateStyle: 'long',
  timeStyle: 'short',
  timeZone: 'UTC',
});

/** Fecha ISO-8601 en hora UTC, o un texto de reserva si falta. */
export function formatDateTime(iso: string | null): string {
  if (!iso) return 'sin fecha';
  const normalized = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return 'sin fecha';
  return dateTimeFormatter.format(date);
}

export function formatQuantity(quantityMilli: number, baseUnit: string): string {
  const value = quantityMilli / 1000;
  const unit = baseUnit === 'unit' ? 'ud' : baseUnit;
  return `${numberFormatter.format(value)} ${unit}`;
}
