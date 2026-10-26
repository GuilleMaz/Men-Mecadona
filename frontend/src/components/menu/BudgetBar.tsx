import { AlertTriangle, PiggyBank, ShoppingBasket, Wallet } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatEuro } from '@/lib/labels';
import type { MenuSummary } from '@/lib/menu';

/** Barra de presupuesto con ticket, consumo, despensa y sobras. */
export function BudgetBar({ menu }: { menu: MenuSummary }) {
  const ratio = menu.budget_cents > 0 ? menu.ticket_cents / menu.budget_cents : 0;
  const percent = Math.round(ratio * 100);
  const nearLimit = ratio >= 0.9;
  const overBudget =
    menu.revalidated_ticket_cents !== null
      ? menu.revalidated_ticket_cents > menu.budget_cents
      : menu.ticket_cents > menu.budget_cents;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <PiggyBank aria-hidden="true" className="size-5 text-primary" />
          Presupuesto
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p>
              <span className="text-lg font-semibold">{formatEuro(menu.ticket_cents)}</span>{' '}
              <span className="text-muted-foreground">
                de {formatEuro(menu.budget_cents)} de presupuesto
              </span>
            </p>
            <p className="font-medium" aria-label={`${percent} % del presupuesto`}>
              {percent} %
            </p>
          </div>
          <div
            role="progressbar"
            aria-label="Presupuesto usado"
            aria-valuemin={0}
            aria-valuemax={menu.budget_cents}
            aria-valuenow={menu.ticket_cents}
            aria-valuetext={`${formatEuro(menu.ticket_cents)} de ${formatEuro(menu.budget_cents)} (${percent} %)`}
            className="h-3 w-full overflow-hidden rounded-full bg-muted"
          >
            <div
              className={`h-full rounded-full transition-[width] ${
                nearLimit ? 'bg-amber-500' : 'bg-primary'
              }`}
              style={{ width: `${Math.min(100, Math.max(0, percent))} %` }}
            />
          </div>
        </div>

        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-md border p-3">
            <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Wallet aria-hidden="true" className="size-3.5" />
              Consumo
            </dt>
            <dd className="font-medium">{formatEuro(menu.consumption_cents)}</dd>
          </div>
          <div className="rounded-md border p-3">
            <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <ShoppingBasket aria-hidden="true" className="size-3.5" />
              Despensa
            </dt>
            <dd className="font-medium">{formatEuro(menu.pantry_consumption_cents)}</dd>
          </div>
          <div className="rounded-md border p-3">
            <dt className="text-xs text-muted-foreground">Sobras</dt>
            <dd className="font-medium">{formatEuro(menu.leftover_value_cents)}</dd>
          </div>
        </dl>

        {nearLimit && !overBudget ? (
          <p
            role="status"
            className="flex items-start gap-2 rounded-md bg-amber-500/10 p-2 text-xs text-amber-900"
          >
            <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            Estás cerca del límite del presupuesto. Los cambios que suban el ticket se rechazarán.
          </p>
        ) : null}

        {overBudget ? (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-md bg-destructive/10 p-2 text-xs text-destructive"
          >
            <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            Los precios actuales elevan el ticket por encima del presupuesto. Revalida o regenera el
            menú antes de comprar.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
