import { AlertTriangle, Clock, RefreshCw, Store, Warehouse } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  formatDateTime,
  formatEuro,
  MENU_STATUS_LABELS,
  PRICE_STATUS_LABELS,
  RELAXATION_LABELS,
} from '@/lib/labels';
import type { MenuDetail, MenuStatus, PriceStatus } from '@/lib/menu';

const STATUS_CLASSES: Record<MenuStatus, string> = {
  optimal: 'border-primary/30 bg-primary/5 text-primary',
  feasible: 'border-border bg-muted text-foreground',
  relaxed: 'border-amber-500/40 bg-amber-500/10 text-amber-900',
};

function StatusBadge({ status }: { status: MenuStatus }) {
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs font-medium ${STATUS_CLASSES[status]}`}
    >
      {MENU_STATUS_LABELS[status] ?? status}
    </span>
  );
}

function PriceBadge({ priceStatus }: { priceStatus: PriceStatus }) {
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
        priceStatus === 'stale'
          ? 'border-amber-500/40 bg-amber-500/10 text-amber-900'
          : 'border-primary/30 bg-primary/5 text-primary'
      }`}
    >
      {PRICE_STATUS_LABELS[priceStatus] ?? priceStatus}
    </span>
  );
}

type MenuHeaderProps = {
  menu: MenuDetail;
  isRevalidating: boolean;
  onRevalidate: () => void;
  onRegenerate: () => void;
};

/** Cabecera del menú: estado, precios, fecha, CP/almacén y relajaciones. */
export function MenuHeader({ menu, isRevalidating, onRevalidate, onRegenerate }: MenuHeaderProps) {
  const stale = menu.price_status === 'stale';
  const delta =
    menu.revalidated_ticket_cents !== null
      ? menu.revalidated_ticket_cents - menu.ticket_cents
      : null;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle>
              <h2 className="text-xl font-semibold">
                Menú de {menu.days} {menu.days === 1 ? 'día' : 'días'} para {menu.people}{' '}
                {menu.people === 1 ? 'persona' : 'personas'}
              </h2>
            </CardTitle>
            <CardDescription>
              Generado el {formatDateTime(menu.created_at)} · Actualizado el{' '}
              {formatDateTime(menu.updated_at)}
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge status={menu.status} />
            <PriceBadge priceStatus={menu.price_status} />
            {menu.timed_out ? (
              <span className="flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-900">
                <Clock aria-hidden="true" className="size-3.5" />
                Tiempo de cálculo agotado
              </span>
            ) : null}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 text-sm">
        <dl className="grid gap-3 sm:grid-cols-3">
          <div className="flex items-start gap-2">
            <Store aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <div>
              <dt className="text-xs text-muted-foreground">Código postal</dt>
              <dd className="font-medium">{menu.postal_code}</dd>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <Warehouse
              aria-hidden="true"
              className="mt-0.5 size-4 shrink-0 text-muted-foreground"
            />
            <div>
              <dt className="text-xs text-muted-foreground">Almacén</dt>
              <dd className="font-medium">{menu.warehouse}</dd>
            </div>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Fecha de los precios</dt>
            <dd className="font-medium">{formatDateTime(menu.prices_captured_at)}</dd>
          </div>
        </dl>

        {menu.timed_out ? (
          <p
            role="status"
            className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-900"
          >
            <Clock aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            El cálculo agotó el tiempo disponible. El menú es válido y respeta el presupuesto, pero
            puede no ser el más barato. Puedes regenerarlo si quieres intentarlo de nuevo.
          </p>
        ) : null}

        {menu.status === 'relaxed' ? (
          <div
            role="status"
            className="space-y-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-900"
          >
            <p className="flex items-center gap-2 font-medium">
              <AlertTriangle aria-hidden="true" className="size-4 shrink-0" />
              Menú válido con relajaciones de variedad
            </p>
            {menu.relaxations.length > 0 ? (
              <ul className="list-disc space-y-1 pl-5">
                {menu.relaxations.map((relaxation) => (
                  <li key={relaxation}>{RELAXATION_LABELS[relaxation] ?? relaxation}</li>
                ))}
              </ul>
            ) : (
              <p>Se han relajado algunos objetivos de variedad para respetar el presupuesto.</p>
            )}
          </div>
        ) : null}

        {stale ? (
          <div
            role="status"
            className="space-y-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-amber-900"
          >
            <div className="space-y-1">
              <p className="flex items-center gap-2 font-medium">
                <AlertTriangle aria-hidden="true" className="size-4 shrink-0" />
                Los precios han cambiado desde que se generó el menú
              </p>
              {menu.revalidated_ticket_cents !== null ? (
                <p>
                  Ticket revalidado: <strong>{formatEuro(menu.revalidated_ticket_cents)}</strong>{' '}
                  (antes {formatEuro(menu.ticket_cents)}
                  {delta !== null
                    ? `, diferencia ${delta >= 0 ? '+' : '−'}${formatEuro(Math.abs(delta))}`
                    : ''}
                  ).
                </p>
              ) : (
                <p>Revisa el ticket antes de comprar.</p>
              )}
              <p className="text-xs">
                El menú guardado y su lista siguen siendo válidos. Revalidar actualiza el cálculo;
                regenerar busca otro menú dentro del presupuesto.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onRevalidate}
                disabled={isRevalidating}
              >
                <RefreshCw
                  aria-hidden="true"
                  className={isRevalidating ? 'animate-spin' : undefined}
                />
                {isRevalidating ? 'Revalidando…' : 'Revalidar precios'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={onRegenerate}>
                Regenerar menú
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onRevalidate}
              disabled={isRevalidating}
            >
              <RefreshCw
                aria-hidden="true"
                className={isRevalidating ? 'animate-spin' : undefined}
              />
              {isRevalidating ? 'Revalidando…' : 'Revalidar precios'}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onRegenerate}>
              Regenerar menú
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
