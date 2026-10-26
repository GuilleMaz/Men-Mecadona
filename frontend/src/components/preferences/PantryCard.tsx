import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LoaderCircle, ShoppingBasket, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  DomainRequestError,
  fetchIngredients,
  fetchPantry,
  updatePantry,
  type PantryItemInput,
} from '@/lib/domain';
import { formatQuantity } from '@/lib/labels';

const selectClassName =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50';

/** Despensa por ingrediente y cantidad en unidad base. */
export function PantryCard() {
  const queryClient = useQueryClient();
  const [ingredientId, setIngredientId] = useState('');
  const [quantity, setQuantity] = useState('');
  const pantryQuery = useQuery({ queryKey: ['pantry'], queryFn: fetchPantry });
  const ingredientsQuery = useQuery({
    queryKey: ['ingredients'],
    queryFn: () => fetchIngredients({ limit: 200 }),
  });
  const mutation = useMutation({
    mutationFn: updatePantry,
    onSuccess: (items) => {
      queryClient.setQueryData(['pantry'], items);
      setQuantity('');
      void queryClient.invalidateQueries({ queryKey: ['pantry'] });
    },
  });

  const items = pantryQuery.data ?? [];
  const ingredients = useMemo(() => ingredientsQuery.data?.items ?? [], [ingredientsQuery.data]);
  const selectedIngredient = useMemo(
    () => ingredients.find((ingredient) => ingredient.id === Number(ingredientId)),
    [ingredients, ingredientId],
  );
  const error =
    mutation.error instanceof DomainRequestError
      ? mutation.error.message
      : mutation.error
        ? 'No se pudo guardar la despensa.'
        : null;

  const baseItems = (): PantryItemInput[] =>
    items.map((item) => ({
      ingredient_id: item.ingredient.id,
      quantity_milli: item.quantity_milli,
    }));

  const handleAdd = () => {
    if (!selectedIngredient || !quantity) {
      return;
    }
    const value = Number(quantity);
    if (!Number.isFinite(value) || value < 0) {
      return;
    }
    const quantityMilli = Math.round(value * 1000);
    const next = baseItems().filter((item) => item.ingredient_id !== selectedIngredient.id);
    next.push({ ingredient_id: selectedIngredient.id, quantity_milli: quantityMilli });
    mutation.mutate(next);
  };

  const handleDelete = (id: number) => {
    mutation.mutate(baseItems().filter((item) => item.ingredient_id !== id));
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShoppingBasket aria-hidden="true" className="size-5 text-primary" />
          Despensa
        </CardTitle>
        <CardDescription>
          Cantidades que ya tienes en casa. Se restan de la necesidad antes de calcular paquetes.
          Indica la cantidad en la unidad base del ingrediente.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_160px_auto] sm:items-end">
          <div className="space-y-2">
            <label htmlFor="pantry-ingredient" className="text-sm font-medium">
              Ingrediente
            </label>
            <select
              id="pantry-ingredient"
              className={selectClassName}
              value={ingredientId}
              onChange={(event) => setIngredientId(event.target.value)}
            >
              <option value="">Selecciona…</option>
              {ingredients.map((ingredient) => (
                <option key={ingredient.id} value={ingredient.id}>
                  {ingredient.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <label htmlFor="pantry-quantity" className="text-sm font-medium">
              Cantidad{selectedIngredient ? ` (${selectedIngredient.base_unit})` : ''}
            </label>
            <Input
              id="pantry-quantity"
              type="number"
              inputMode="decimal"
              min={0}
              step={0.01}
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              disabled={!selectedIngredient}
            />
          </div>
          <Button
            type="button"
            onClick={handleAdd}
            disabled={!selectedIngredient || !quantity || mutation.isPending}
          >
            Añadir
          </Button>
        </div>

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        {pantryQuery.isPending || ingredientsQuery.isPending ? (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
            Cargando despensa…
          </p>
        ) : null}
        {pantryQuery.isError || ingredientsQuery.isError ? (
          <p role="alert" className="text-sm text-destructive">
            No se pudo cargar la despensa.
          </p>
        ) : null}

        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">La despensa está vacía.</p>
        ) : (
          <ul className="space-y-2">
            {items.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-3 rounded-md border p-2 text-sm"
              >
                <span>
                  {item.ingredient.name}:{' '}
                  <span className="font-medium">
                    {formatQuantity(item.quantity_milli, item.ingredient.base_unit)}
                  </span>
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`Quitar ${item.ingredient.name} de la despensa`}
                  onClick={() => handleDelete(item.ingredient.id)}
                  disabled={mutation.isPending}
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
