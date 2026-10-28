import { Lock, LockOpen, Plus, RefreshCw, Shuffle, ThumbsDown, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  COURSE_LABELS,
  formatEuro,
  formatQuantity,
  mealLabel,
  proteinLabel,
  tagLabel,
} from '@/lib/labels';
import type { MenuEntry } from '@/lib/menu';

type MenuEntryCardProps = {
  entry: MenuEntry;
  isBusy: boolean;
  hasComplement?: boolean;
  onToggleLock: () => void;
  onSwap: () => void;
  onExclude: () => void;
  onRegenerate: () => void;
  onAddComplement?: () => void;
  onRemoveComplement?: () => void;
};

/** Tarjeta de una comida o cena del menú con sus acciones. */
export function MenuEntryCard({
  entry,
  isBusy,
  hasComplement = false,
  onToggleLock,
  onSwap,
  onExclude,
  onRegenerate,
  onAddComplement,
  onRemoveComplement,
}: MenuEntryCardProps) {
  return (
    <Card className="h-full gap-3 py-4" aria-busy={isBusy}>
      <CardHeader className="space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <span>{mealLabel(entry.slot)}</span>
              <span aria-hidden="true"> · </span>
              <span>{COURSE_LABELS[entry.course] ?? entry.course}</span>
            </p>
            <CardTitle>
              <h4 className="text-base font-semibold">{entry.dish_name}</h4>
            </CardTitle>
          </div>
          {entry.locked ? (
            <span className="flex items-center gap-1 rounded-full border border-primary/30 bg-primary/5 px-2 py-0.5 text-xs font-medium text-primary">
              <Lock aria-hidden="true" className="size-3" />
              Bloqueado
            </span>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="space-y-3 text-sm">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p>
            <span className="text-xs text-muted-foreground">Coste de la entrada: </span>
            <span className="font-semibold">{formatEuro(entry.entry_consumption_cents)}</span>
          </p>
          {entry.protein_source ? (
            <p className="text-xs text-muted-foreground">
              Proteína: {proteinLabel(entry.protein_source)}
            </p>
          ) : null}
        </div>

        {entry.tags.length > 0 ? (
          <ul className="flex flex-wrap gap-1.5" aria-label="Etiquetas del plato">
            {entry.tags.map((tag) => (
              <li key={tag} className="rounded bg-muted px-1.5 py-0.5 text-xs">
                {tagLabel(tag)}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">Sin etiquetas.</p>
        )}

        {entry.ingredients.length > 0 ? (
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer font-medium text-foreground">
              Ingredientes ({entry.ingredients.length})
            </summary>
            <ul className="mt-2 space-y-1">
              {entry.ingredients.map((ingredient) => (
                <li key={ingredient.ingredient_id} className="flex justify-between gap-2">
                  <span>{ingredient.ingredient_name}</span>
                  <span>{formatQuantity(ingredient.used_milli, ingredient.base_unit)}</span>
                </li>
              ))}
            </ul>
          </details>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isBusy}
            aria-label={`${entry.locked ? 'Desbloquear' : 'Bloquear'} ${entry.dish_name}`}
            onClick={onToggleLock}
          >
            {entry.locked ? (
              <LockOpen aria-hidden="true" className="size-4" />
            ) : (
              <Lock aria-hidden="true" className="size-4" />
            )}
            {entry.locked ? 'Desbloquear' : 'Bloquear'}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isBusy}
            aria-label={`Cambiar ${entry.dish_name}`}
            onClick={onSwap}
          >
            <Shuffle aria-hidden="true" className="size-4" />
            Cambiar
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={isBusy}
            aria-label={`No me gusta ${entry.dish_name}`}
            onClick={onExclude}
          >
            <ThumbsDown aria-hidden="true" className="size-4" />
            No me gusta
          </Button>
          {entry.course === 'main' && !hasComplement && onAddComplement ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={isBusy}
              aria-label={`Añadir acompañamiento a ${entry.dish_name}`}
              onClick={onAddComplement}
            >
              <Plus aria-hidden="true" className="size-4" />
              Añadir acompañamiento
            </Button>
          ) : null}
          {entry.course === 'complement' && onRemoveComplement ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={isBusy}
              aria-label={`Quitar acompañamiento ${entry.dish_name}`}
              onClick={onRemoveComplement}
            >
              <Trash2 aria-hidden="true" className="size-4" />
              Quitar
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={isBusy}
            aria-label={`Regenerar menú desde ${entry.dish_name}`}
            onClick={onRegenerate}
          >
            <RefreshCw aria-hidden="true" className="size-4" />
            Regenerar
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
