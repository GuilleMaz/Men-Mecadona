import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  Eye,
  LoaderCircle,
  Search,
  ThumbsDown,
  UtensilsCrossed,
} from 'lucide-react';
import { useMemo, useState } from 'react';

import { DishCostCard } from '@/components/dishes/DishCostCard';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  createExclusion,
  DomainRequestError,
  fetchAllergens,
  fetchDish,
  fetchDishes,
  fetchProfile,
  type DishSummary,
} from '@/lib/domain';
import {
  euroFormatter,
  EXCLUSION_REASON_LABELS,
  formatQuantity,
  mealLabel,
  tagLabel,
} from '@/lib/labels';

type MealFilter = 'all' | 'lunch' | 'dinner';

const selectClassName =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50';

function DishCard({
  dish,
  allergenLabels,
  onOpen,
  onDislike,
  isDisliking,
}: {
  dish: DishSummary;
  allergenLabels: Map<string, string>;
  onOpen: () => void;
  onDislike: () => void;
  isDisliking: boolean;
}) {
  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="space-y-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base">{dish.name}</CardTitle>
          <span
            className={`shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium ${
              dish.eligible
                ? 'border-primary/30 bg-primary/5 text-primary'
                : 'border-amber-500/40 bg-amber-500/10 text-amber-800'
            }`}
          >
            {dish.eligible ? 'Elegible' : 'No elegible'}
          </span>
        </div>
        <CardDescription>{dish.description}</CardDescription>
      </CardHeader>
      <CardContent className="mt-auto space-y-3 text-sm">
        <div className="flex flex-wrap gap-1.5">
          {dish.meal_types.map((meal) => (
            <span key={meal} className="rounded bg-muted px-1.5 py-0.5 text-xs">
              {mealLabel(meal)}
            </span>
          ))}
          {dish.light ? (
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs">Ligero</span>
          ) : null}
          {dish.tags.map((tag) => (
            <span key={tag} className="rounded bg-muted px-1.5 py-0.5 text-xs">
              {tagLabel(tag)}
            </span>
          ))}
        </div>

        {dish.allergens.length > 0 ? (
          <p className="text-xs text-muted-foreground">
            <span className="font-medium">Alérgenos:</span>{' '}
            {dish.allergens.map((code) => allergenLabels.get(code) ?? code).join(', ')}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">Sin alérgenos declarados.</p>
        )}

        {!dish.eligible ? (
          <p className="text-xs text-amber-800">
            {dish.exclusion_reasons
              .map((reason) => EXCLUSION_REASON_LABELS[reason] ?? reason)
              .join(' · ')}
          </p>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onOpen}>
            <Eye aria-hidden="true" className="size-4" />
            Ver ingredientes
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onDislike}
            disabled={isDisliking}
          >
            <ThumbsDown aria-hidden="true" className="size-4" />
            No me gusta
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function DishDetailCard({ dishId }: { dishId: number }) {
  const queryClient = useQueryClient();
  const detailQuery = useQuery({
    queryKey: ['dish', dishId],
    queryFn: () => fetchDish(dishId),
  });
  const mutation = useMutation({
    mutationFn: createExclusion,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['dishes'] }),
        queryClient.invalidateQueries({ queryKey: ['dish', dishId] }),
        queryClient.invalidateQueries({ queryKey: ['exclusions'] }),
      ]);
    },
  });
  const detail = detailQuery.data;
  const error =
    mutation.error instanceof DomainRequestError
      ? mutation.error.message
      : mutation.error
        ? 'No se pudo guardar la exclusión.'
        : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {detail ? detail.name : 'Composición del plato'}
        </CardTitle>
        <CardDescription>Ingredientes y productos asociados. Sin pasos de cocina.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {detailQuery.isPending ? (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
            Cargando composición…
          </p>
        ) : null}
        {detailQuery.isError ? (
          <p role="alert" className="text-sm text-destructive">
            No se pudo cargar la composición del plato.
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        {detail ? (
          <ul className="space-y-3">
            {detail.ingredients.map(({ ingredient, quantity_milli, products }) => (
              <li
                key={ingredient.id}
                className="flex flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="space-y-1">
                  <p className="font-medium">{ingredient.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatQuantity(quantity_milli, ingredient.base_unit)} para{' '}
                    {detail.base_servings} raciones
                  </p>
                  {products.length > 0 ? (
                    <p className="text-xs text-muted-foreground">
                      {products
                        .slice(0, 2)
                        .map(
                          (product) =>
                            `${product.name}${
                              product.package_price_cents !== null
                                ? ` (${euroFormatter.format(product.package_price_cents / 100)})`
                                : ''
                            }`,
                        )
                        .join(' · ')}
                    </p>
                  ) : (
                    <p className="text-xs text-amber-800">Sin producto asociado.</p>
                  )}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={mutation.isPending}
                  onClick={() => mutation.mutate({ ingredient_id: ingredient.id })}
                >
                  <ThumbsDown aria-hidden="true" className="size-4" />
                  No me gusta este ingrediente
                </Button>
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function DishesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [mealFilter, setMealFilter] = useState<MealFilter>('all');
  const [tagFilter, setTagFilter] = useState('');
  const [lightOnly, setLightOnly] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [selectedDishId, setSelectedDishId] = useState<number | null>(null);

  const dishesQuery = useQuery({
    queryKey: ['dishes', search, mealFilter, tagFilter, lightOnly, showAll],
    queryFn: () =>
      fetchDishes({
        q: search.trim() || undefined,
        mealType: mealFilter === 'all' ? undefined : mealFilter,
        tag: tagFilter || undefined,
        light: lightOnly ? true : undefined,
        onlyEligible: !showAll,
        limit: 100,
      }),
  });
  const tagsQuery = useQuery({
    queryKey: ['dishes', 'tags'],
    queryFn: () => fetchDishes({ onlyEligible: false, limit: 100 }),
  });
  const allergensQuery = useQuery({ queryKey: ['allergens'], queryFn: fetchAllergens });
  const profileQuery = useQuery({ queryKey: ['profile'], queryFn: fetchProfile });
  const people = profileQuery.data?.people ?? 2;
  const dishMutation = useMutation({
    mutationFn: createExclusion,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['dishes'] }),
        queryClient.invalidateQueries({ queryKey: ['exclusions'] }),
      ]);
    },
  });

  const allergenLabels = useMemo(() => {
    const map = new Map<string, string>();
    for (const allergen of allergensQuery.data ?? []) {
      map.set(allergen.code, allergen.name);
    }
    return map;
  }, [allergensQuery.data]);

  const tags = useMemo(() => {
    const found = new Set<string>();
    for (const dish of tagsQuery.data?.items ?? []) {
      for (const tag of dish.tags) {
        found.add(tag);
      }
    }
    return [...found].sort();
  }, [tagsQuery.data]);

  const dishes = dishesQuery.data?.items ?? [];
  const mutationError =
    dishMutation.error instanceof DomainRequestError
      ? dishMutation.error.message
      : dishMutation.error
        ? 'No se pudo guardar la exclusión.'
        : null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Catálogo de platos</h2>
        <p className="text-sm text-muted-foreground">
          Platos con sus ingredientes, etiquetas y alérgenos. Nunca instrucciones de elaboración.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UtensilsCrossed aria-hidden="true" className="size-5 text-primary" />
            Buscar y filtrar
          </CardTitle>
          <CardDescription>
            Las preferencias excluyen platos del catálogo visible. Puedes mostrar los no elegibles
            para revisarlos.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="dish-search">Buscar plato</Label>
              <div className="relative">
                <Search
                  aria-hidden="true"
                  className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                />
                <Input
                  id="dish-search"
                  className="pl-9"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Pollo, arroz, lentejas…"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="meal-filter">Momento</Label>
              <select
                id="meal-filter"
                className={selectClassName}
                value={mealFilter}
                onChange={(event) => setMealFilter(event.target.value as MealFilter)}
              >
                <option value="all">Comida y cena</option>
                <option value="lunch">Comida</option>
                <option value="dinner">Cena</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="tag-filter">Etiqueta</Label>
              <select
                id="tag-filter"
                className={selectClassName}
                value={tagFilter}
                onChange={(event) => setTagFilter(event.target.value)}
              >
                <option value="">Todas</option>
                {tags.map((tag) => (
                  <option key={tag} value={tag}>
                    {tagLabel(tag)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                className="size-4 rounded border-input"
                checked={lightOnly}
                onChange={(event) => setLightOnly(event.target.checked)}
              />
              Solo platos ligeros
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                className="size-4 rounded border-input"
                checked={showAll}
                onChange={(event) => setShowAll(event.target.checked)}
              />
              Mostrar también los no elegibles
            </label>
          </div>
        </CardContent>
      </Card>

      {mutationError ? (
        <p role="alert" className="text-sm text-destructive">
          {mutationError}
        </p>
      ) : null}

      {dishesQuery.isPending ? (
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
          Cargando platos…
        </p>
      ) : null}

      {dishesQuery.isError ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
        >
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <div className="space-y-2">
            <p>No se pudo consultar el catálogo de platos.</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void dishesQuery.refetch()}
            >
              Reintentar
            </Button>
          </div>
        </div>
      ) : null}

      {!dishesQuery.isPending && !dishesQuery.isError ? (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {dishesQuery.data?.total ?? 0} platos encontrados.
            {!showAll ? ' Se ocultan los no elegibles.' : ''}
          </p>
          {dishes.length === 0 ? (
            <Card>
              <CardContent className="space-y-2 py-6 text-sm text-muted-foreground">
                <p>No hay platos que coincidan con los filtros.</p>
                {!showAll ? (
                  <p>
                    Prueba a mostrar los no elegibles o revisa tus exclusiones y alérgenos en
                    Ajustes.
                  </p>
                ) : null}
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {dishes.map((dish) => (
                <DishCard
                  key={dish.id}
                  dish={dish}
                  allergenLabels={allergenLabels}
                  isDisliking={dishMutation.isPending}
                  onOpen={() => setSelectedDishId(dish.id)}
                  onDislike={() => dishMutation.mutate({ dish_id: dish.id })}
                />
              ))}
            </div>
          )}
        </div>
      ) : null}

      {selectedDishId !== null ? (
        <div className="space-y-4">
          <DishDetailCard dishId={selectedDishId} />
          <DishCostCard dishId={selectedDishId} people={people} />
        </div>
      ) : null}

      <p className="text-xs text-muted-foreground">
        Alérgenos mostrados con la lista canónica de la app. Confirma siempre el etiquetado del
        producto antes de consumir.
      </p>
    </div>
  );
}
