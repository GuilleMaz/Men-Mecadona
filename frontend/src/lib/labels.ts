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

export function formatQuantity(quantityMilli: number, baseUnit: string): string {
  const value = quantityMilli / 1000;
  const unit = baseUnit === 'unit' ? 'ud' : baseUnit;
  return `${numberFormatter.format(value)} ${unit}`;
}
