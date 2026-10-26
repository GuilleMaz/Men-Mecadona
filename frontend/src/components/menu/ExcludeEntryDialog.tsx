import { useMutation } from '@tanstack/react-query';
import { AlertTriangle, LoaderCircle } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import { DomainRequestError } from '@/lib/domain';
import { mealLabel } from '@/lib/labels';
import { excludeEntry, type ExclusionScope, type MenuDetail, type MenuEntry } from '@/lib/menu';

type ExcludeEntryDialogProps = {
  open: boolean;
  menuId: number;
  entry: MenuEntry | null;
  onClose: () => void;
  onExcluded: (menu: MenuDetail) => void;
};

/** «No me gusta» con alcance de menú o de perfil. */
export function ExcludeEntryDialog({
  open,
  menuId,
  entry,
  onClose,
  onExcluded,
}: ExcludeEntryDialogProps) {
  const [scope, setScope] = useState<ExclusionScope>('menu');

  const mutation = useMutation({
    mutationFn: (value: ExclusionScope) => excludeEntry(menuId, entry!.id, value),
    onSuccess: (menu) => {
      onExcluded(menu);
      onClose();
    },
  });

  if (!entry) return null;

  const error =
    mutation.error instanceof DomainRequestError
      ? mutation.error
      : mutation.error
        ? new DomainRequestError('No se pudo guardar el cambio.')
        : null;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`No me gusta «${entry.dish_name}»`}
      description={`${mealLabel(entry.slot)} del día ${entry.day_index + 1}. Cambiaremos este plato por otro plato elegible.`}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={mutation.isPending}>
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={() => mutation.mutate(scope)}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? (
              <LoaderCircle aria-hidden="true" className="animate-spin" />
            ) : null}
            {mutation.isPending ? 'Guardando…' : 'No me gusta'}
          </Button>
        </>
      }
    >
      <fieldset className="space-y-2" disabled={mutation.isPending}>
        <legend className="mb-2 font-medium">¿Dónde quieres excluirlo?</legend>
        <label
          htmlFor="exclude-scope-menu"
          className="flex cursor-pointer items-start gap-3 rounded-md border p-3 hover:bg-accent"
        >
          <input
            id="exclude-scope-menu"
            type="radio"
            name="exclude-scope"
            value="menu"
            checked={scope === 'menu'}
            onChange={() => setScope('menu')}
            className="mt-1 size-4"
          />
          <span>
            <span className="block font-medium">Solo en este menú</span>
            <span className="block text-xs text-muted-foreground">
              Se cambia este plato ahora; tu perfil no cambia.
            </span>
          </span>
        </label>
        <label
          htmlFor="exclude-scope-profile"
          className="flex cursor-pointer items-start gap-3 rounded-md border p-3 hover:bg-accent"
        >
          <input
            id="exclude-scope-profile"
            type="radio"
            name="exclude-scope"
            value="profile"
            checked={scope === 'profile'}
            onChange={() => setScope('profile')}
            className="mt-1 size-4"
          />
          <span>
            <span className="block font-medium">En este menú y en los futuros</span>
            <span className="block text-xs text-muted-foreground">
              Añade el plato a tus exclusiones del perfil. No afecta a alérgenos.
            </span>
          </span>
        </label>
      </fieldset>

      {error ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-destructive"
        >
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <p>{error.message}</p>
        </div>
      ) : null}
    </Dialog>
  );
}
