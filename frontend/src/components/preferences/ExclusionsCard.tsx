import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Ban, LoaderCircle, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  createExclusion,
  deleteExclusion,
  DomainRequestError,
  fetchDishes,
  fetchExclusions,
  fetchIngredients,
  type Exclusion,
  type ExclusionCreate,
} from '@/lib/domain';
import { tagLabel } from '@/lib/labels';

type ExclusionType = 'ingredient' | 'dish' | 'tag';

const selectClassName =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50';

const kindLabels: Record<ExclusionType, string> = {
  ingredient: 'Ingrediente',
  dish: 'Plato',
  tag: 'Etiqueta',
};

function exclusionLabel(exclusion: Exclusion): string {
  return exclusion.kind === 'tag' ? tagLabel(exclusion.tag ?? '') : exclusion.label;
}

/** Exclusiones persistentes por ingrediente, plato o etiqueta. */
export function ExclusionsCard() {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<ExclusionType>('ingredient');
  const [target, setTarget] = useState('');
  const exclusionsQuery = useQuery({ queryKey: ['exclusions'], queryFn: fetchExclusions });
  const ingredientsQuery = useQuery({
    queryKey: ['ingredients'],
    queryFn: () => fetchIngredients({ limit: 200 }),
  });
  const dishesQuery = useQuery({
    queryKey: ['dishes', 'all'],
    queryFn: () => fetchDishes({ onlyEligible: false, limit: 100 }),
  });
  const createMutation = useMutation({
    mutationFn: createExclusion,
    onSuccess: async () => {
      setTarget('');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['exclusions'] }),
        queryClient.invalidateQueries({ queryKey: ['dishes'] }),
      ]);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteExclusion,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['exclusions'] }),
        queryClient.invalidateQueries({ queryKey: ['dishes'] }),
      ]);
    },
  });

  const tags = useMemo(() => {
    const found = new Set<string>();
    for (const dish of dishesQuery.data?.items ?? []) {
      for (const tag of dish.tags) {
        found.add(tag);
      }
    }
    return [...found].sort();
  }, [dishesQuery.data]);

  const error =
    createMutation.error instanceof DomainRequestError
      ? createMutation.error.message
      : deleteMutation.error instanceof DomainRequestError
        ? deleteMutation.error.message
        : createMutation.error || deleteMutation.error
          ? 'No se pudo actualizar la exclusión.'
          : null;

  const handleAdd = () => {
    let payload: ExclusionCreate;
    if (kind === 'tag') {
      payload = { tag: target };
    } else if (kind === 'dish') {
      payload = { dish_id: Number(target) };
    } else {
      payload = { ingredient_id: Number(target) };
    }
    createMutation.mutate(payload);
  };

  const targets =
    kind === 'ingredient'
      ? (ingredientsQuery.data?.items ?? []).map((ingredient) => ({
          value: String(ingredient.id),
          label: ingredient.name,
        }))
      : kind === 'dish'
        ? (dishesQuery.data?.items ?? []).map((dish) => ({
            value: String(dish.id),
            label: dish.name,
          }))
        : tags.map((tag) => ({ value: tag, label: tagLabel(tag) }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Ban aria-hidden="true" className="size-5 text-primary" />
          Exclusiones
        </CardTitle>
        <CardDescription>
          «No me gusta» persistente por ingrediente, plato o etiqueta. No elimina alérgenos.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-[160px_1fr_auto] sm:items-end">
          <div className="space-y-2">
            <label htmlFor="exclusion-kind" className="text-sm font-medium">
              Tipo
            </label>
            <select
              id="exclusion-kind"
              className={selectClassName}
              value={kind}
              onChange={(event) => {
                setKind(event.target.value as ExclusionType);
                setTarget('');
              }}
            >
              <option value="ingredient">Ingrediente</option>
              <option value="dish">Plato</option>
              <option value="tag">Etiqueta</option>
            </select>
          </div>
          <div className="space-y-2">
            <label htmlFor="exclusion-target" className="text-sm font-medium">
              {kindLabels[kind]} a excluir
            </label>
            <select
              id="exclusion-target"
              className={selectClassName}
              value={target}
              onChange={(event) => setTarget(event.target.value)}
            >
              <option value="">Selecciona…</option>
              {targets.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <Button type="button" onClick={handleAdd} disabled={!target || createMutation.isPending}>
            <Ban aria-hidden="true" className="size-4" />
            Excluir
          </Button>
        </div>

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        {exclusionsQuery.isPending ? (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
            Cargando exclusiones…
          </p>
        ) : null}
        {exclusionsQuery.isError ? (
          <p role="alert" className="text-sm text-destructive">
            No se pudieron cargar las exclusiones.
          </p>
        ) : null}

        {(exclusionsQuery.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">No hay exclusiones guardadas.</p>
        ) : (
          <ul className="space-y-2">
            {(exclusionsQuery.data ?? []).map((exclusion) => (
              <li
                key={exclusion.id}
                className="flex items-center justify-between gap-3 rounded-md border p-2 text-sm"
              >
                <span>
                  <span className="text-muted-foreground">{kindLabels[exclusion.kind]}: </span>
                  {exclusionLabel(exclusion)}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`Quitar exclusión de ${exclusionLabel(exclusion)}`}
                  onClick={() => deleteMutation.mutate(exclusion.id)}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 aria-hidden="true" className="size-4" />
                  Quitar
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
