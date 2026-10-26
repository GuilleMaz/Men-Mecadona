import { CheckCircle2, Scale, Wallet } from 'lucide-react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatEuro } from '@/lib/labels';
import type { ShoppingList } from '@/lib/menu';

/** Barra inferior fija con el total del ticket y lo marcado. */
export function ShoppingStickyTotal({ list }: { list: ShoppingList }) {
  const remaining = list.ticket_cents - list.checked_total_cents;

  return (
    <aside
      aria-label="Resumen fijo de la compra"
      className="sticky bottom-0 z-10 -mx-4 border-t bg-card/95 px-4 py-3 shadow-[0_-4px_12px_rgba(0,0,0,0.08)] backdrop-blur print:hidden"
    >
      <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs text-muted-foreground">Total del ticket</p>
          <p className="text-xl font-semibold">{formatEuro(list.ticket_cents)}</p>
        </div>
        <div aria-live="polite" className="text-sm">
          <p className="flex items-center gap-1.5">
            <CheckCircle2 aria-hidden="true" className="size-4 text-primary" />
            {list.checked_count} de {list.item_count} productos marcados
          </p>
          <p className="text-xs text-muted-foreground">
            {formatEuro(list.checked_total_cents)} marcado · {formatEuro(Math.max(0, remaining))}{' '}
            pendiente
          </p>
        </div>
        <div className="text-sm">
          <p className="text-xs text-muted-foreground">Presupuesto</p>
          <p className="font-medium">{formatEuro(list.budget_cents)}</p>
        </div>
      </div>
    </aside>
  );
}

/** Totales, coste por comida/día/persona e identidad contable. */
export function ShoppingTotals({ list }: { list: ShoppingList }) {
  const sectionsTotal = list.sections.reduce((sum, section) => sum + section.subtotal_cents, 0);
  const ticketMatches = sectionsTotal === list.ticket_cents;
  const identityHolds =
    list.ticket_cents + list.pantry_consumption_cents ===
    list.consumption_cents + list.leftover_value_cents;

  return (
    <Card className="print:break-inside-avoid">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Scale aria-hidden="true" className="size-5 text-primary" />
          <h2 className="text-base font-semibold">Resumen de la compra</h2>
        </CardTitle>
        <CardDescription>
          El ticket de la lista coincide céntimo a céntimo con el coste guardado del menú.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-md border p-3">
            <dt className="text-xs text-muted-foreground">Ticket</dt>
            <dd className="text-lg font-semibold">{formatEuro(list.ticket_cents)}</dd>
          </div>
          <div className="rounded-md border p-3">
            <dt className="text-xs text-muted-foreground">Presupuesto</dt>
            <dd className="text-lg font-semibold">{formatEuro(list.budget_cents)}</dd>
          </div>
          <div className="rounded-md border p-3">
            <dt className="text-xs text-muted-foreground">Consumo</dt>
            <dd className="font-medium">{formatEuro(list.consumption_cents)}</dd>
          </div>
          <div className="rounded-md border p-3">
            <dt className="text-xs text-muted-foreground">Despensa</dt>
            <dd className="font-medium">{formatEuro(list.pantry_consumption_cents)}</dd>
          </div>
          <div className="rounded-md border p-3">
            <dt className="text-xs text-muted-foreground">Sobras</dt>
            <dd className="font-medium">{formatEuro(list.leftover_value_cents)}</dd>
          </div>
          <div className="rounded-md border p-3">
            <dt className="text-xs text-muted-foreground">Marcado</dt>
            <dd className="font-medium">
              {formatEuro(list.checked_total_cents)}{' '}
              <span className="text-xs font-normal text-muted-foreground">
                ({list.checked_count}/{list.item_count})
              </span>
            </dd>
          </div>
        </dl>

        <div className="rounded-md border p-3">
          <h2 className="flex items-center gap-2 font-medium">
            <Wallet aria-hidden="true" className="size-4 text-primary" />
            Coste por comida, día y persona
          </h2>
          <dl className="mt-2 grid gap-3 sm:grid-cols-3">
            <div>
              <dt className="text-xs text-muted-foreground">Por comida o cena</dt>
              <dd className="font-semibold">{formatEuro(list.cost_per_meal_cents)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Por día</dt>
              <dd className="font-semibold">{formatEuro(list.cost_per_day_cents)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Por persona y día</dt>
              <dd className="font-semibold">{formatEuro(list.cost_per_person_day_cents)}</dd>
            </div>
          </dl>
        </div>

        <div className="space-y-1 rounded-md bg-muted/60 p-3">
          <h2 className="font-medium">Identidad contable</h2>
          <p data-testid="ticket-sections-total" className="text-muted-foreground">
            Ticket {formatEuro(list.ticket_cents)} = suma de subtotales {formatEuro(sectionsTotal)}
          </p>
          <p className="text-xs text-muted-foreground">
            {ticketMatches
              ? 'La lista suma exactamente el ticket.'
              : 'La lista no suma el ticket; vuelve a cargarla antes de comprar.'}
          </p>
          <p data-testid="accounting-identity" className="text-muted-foreground">
            {formatEuro(list.ticket_cents)} de ticket + {formatEuro(list.pantry_consumption_cents)}{' '}
            de despensa = {formatEuro(list.consumption_cents)} de consumo +{' '}
            {formatEuro(list.leftover_value_cents)} de sobras
          </p>
          <p className="text-xs text-muted-foreground">
            {identityHolds
              ? 'La identidad del menú guardado se cumple.'
              : 'Los importes no cuadran; vuelve a cargar la lista antes de comprar.'}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
