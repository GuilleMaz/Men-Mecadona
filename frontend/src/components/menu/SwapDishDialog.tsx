import { useMutation, useQuery } from '@tanstack/react-query';
import { AlertTriangle, LoaderCircle } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import { DomainRequestError, fetchDishes } from '@/lib/domain';
import { mealLabel, tagLabel } from '@/lib/labels';
import { swapEntry, type MenuDetail, type MenuEntry } from '@/lib/menu';

type SwapDishDialogProps = {
  open: boolean;
  menuId: number;
  entry: MenuEntry | null;
  onClose: () => void;
  onSwapped: (menu: MenuDetail) => void;
};

/** Diálogo para cambiar un plato por otro elegible del mismo hueco. */
export function SwapDishDialog({ open, menuId, entry, onClose, onSwapped }: SwapDishDialogProps) {
  const [selectedDishId, setSelectedDishId] = useState<number | null>(null);

  const dishesQuery = useQuery({
    queryKey: ['dishes', 'swap', entry?.id, entry?.slot],
    queryFn: () => fetchDishes({ mealType: entry!.slot, onlyEligible: true, limit: 100 }),
    enabled: open && entry !== null,
  });

  const mutation = useMutation({
    mutationFn: (dishId: number) => swapEntry(menuId, entry!.id, dishId),
    onSuccess: (menu) => {
      onSwapped(menu);
      onClose();
    },
  });

  if (!entry) return null;

  const dishes = (dishesQuery.data?.items ?? []).filter((dish) => dish.id !== entry.dish_id);
  const error =
    mutation.error instanceof DomainRequestError
      ? mutation.error
      : mutation.error
        ? new DomainRequestError('No se pudo cambiar el plato.')
        : null;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`Cambiar ${mealLabel(entry.slot).toLowerCase()}`}
      description={`Platos elegibles para ${mealLabel(entry.slot).toLowerCase()} del día ${entry.day_index + 1}. Se respetan tus alérgenos, exclusiones y el presupuesto.`}
      className="max-w-xl"
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={mutation.isPending}>
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={() => {
              if (selectedDishId !== null) mutation.mutate(selectedDishId);
            }}
            disabled={selectedDishId === null || mutation.isPending}
          >
            {mutation.isPending ? (
              <LoaderCircle aria-hidden="true" className="animate-spin" />
            ) : null}
            {mutation.isPending ? 'Cambiando…' : 'Cambiar plato'}
          </Button>
        </>
      }
    >
      {dishesQuery.isPending ? (
        <p role="status" className="flex items-center gap-2 text-muted-foreground">
          <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
          Cargando platos elegibles…
        </p>
      ) : null}

      {dishesQuery.isError ? (
        <div role="alert" className="space-y-2 text-destructive">
          <p>No se pudieron cargar los platos elegibles.</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void dishesQuery.refetch()}
          >
            Reintentar
          </Button>
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-destructive"
        >
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <div className="space-y-1">
            <p>{error.message}</p>
            {error.code === 'BUDGET_EXCEEDED' ? (
              <p className="text-xs">
                El cambio supera el presupuesto y no se ha aplicado. Prueba con otro plato o
                regenera el menú.
              </p>
            ) : null}
            {error.code === 'NO_FEASIBLE_MENU' ? (
              <p className="text-xs">
                No hay combinación válida con este cambio. Revisa bloqueos y repeticiones.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      {!dishesQuery.isPending && !dishesQuery.isError ? (
        dishes.length === 0 ? (
          <p className="text-muted-foreground">
            No hay otros platos elegibles para este hueco. Revisa tus exclusiones y alérgenos en
            Ajustes.
          </p>
        ) : (
          <fieldset disabled={mutation.isPending} className="space-y-2">
            <legend className="mb-2 font-medium">
              Elige un plato para {mealLabel(entry.slot).toLowerCase()}
            </legend>
            <ul className="max-h-72 space-y-2 overflow-y-auto pr-1">
              {dishes.map((dish) => (
                <li key={dish.id}>
                  <label
                    htmlFor={`swap-dish-${dish.id}`}
                    className={`flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors hover:bg-accent ${
                      selectedDishId === dish.id ? 'border-primary bg-primary/5' : ''
                    }`}
                  >
                    <input
                      id={`swap-dish-${dish.id}`}
                      type="radio"
                      name="swap-dish"
                      value={dish.id}
                      checked={selectedDishId === dish.id}
                      onChange={() => setSelectedDishId(dish.id)}
                      className="mt-1 size-4"
                    />
                    <span className="space-y-1">
                      <span className="block font-medium">{dish.name}</span>
                      {dish.tags.length > 0 ? (
                        <span className="flex flex-wrap gap-1">
                          {dish.tags.map((tag) => (
                            <span key={tag} className="rounded bg-muted px-1.5 py-0.5 text-xs">
                              {tagLabel(tag)}
                            </span>
                          ))}
                        </span>
                      ) : null}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
        )
      ) : null}
    </Dialog>
  );
}
