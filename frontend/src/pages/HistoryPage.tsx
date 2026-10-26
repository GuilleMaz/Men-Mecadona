import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  ArrowRight,
  History,
  LoaderCircle,
  ShoppingBasket,
  UtensilsCrossed,
} from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatDateTime, formatEuro, MENU_STATUS_LABELS, PRICE_STATUS_LABELS } from '@/lib/labels';
import { fetchMenus, type MenuStatus } from '@/lib/menu';

const PAGE_SIZE = 10;

const STATUS_CLASSES: Record<MenuStatus, string> = {
  optimal: 'border-primary/30 bg-primary/5 text-primary',
  feasible: 'border-border bg-muted text-foreground',
  relaxed: 'border-amber-500/40 bg-amber-500/10 text-amber-900',
};

/** Historial inmutable de menús guardados, del más reciente al más antiguo. */
export function HistoryPage() {
  const [offset, setOffset] = useState(0);
  const historyQuery = useQuery({
    queryKey: ['menus', { limit: PAGE_SIZE, offset }],
    queryFn: () => fetchMenus({ limit: PAGE_SIZE, offset }),
  });

  if (historyQuery.isPending) {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
        Cargando historial de menús…
      </p>
    );
  }

  if (historyQuery.isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>No se pudo cargar el historial</CardTitle>
          <CardDescription>
            Comprueba que la API local esté en marcha y vuelve a intentarlo.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button type="button" variant="outline" onClick={() => void historyQuery.refetch()}>
            Reintentar
          </Button>
        </CardContent>
      </Card>
    );
  }

  const page = historyQuery.data;
  const hasPrevious = offset > 0;
  const hasNext = page !== undefined && offset + page.items.length < page.total;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-2xl font-semibold">
            <History aria-hidden="true" className="size-6 text-primary" />
            Historial de menús
          </h2>
          <p className="text-sm text-muted-foreground">
            Cada menú conserva el nombre y el coste de sus platos aunque el catálogo cambie después.
          </p>
        </div>
        <Button asChild>
          <Link to="/">
            <UtensilsCrossed aria-hidden="true" />
            Crear menú
          </Link>
        </Button>
      </div>

      {page.items.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Todavía no hay menús guardados</CardTitle>
            <CardDescription>
              Genera un menú y aparecerá aquí con su ticket y su lista de la compra.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link to="/">Crear el primer menú</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <section aria-label="Menús guardados">
          <ul className="grid gap-3 md:grid-cols-2">
            {page.items.map((menu) => (
              <li key={menu.id}>
                <Card className="h-full print:break-inside-avoid">
                  <CardHeader>
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="space-y-1">
                        <CardTitle>
                          <h3 className="text-base font-semibold">Menú #{menu.id}</h3>
                        </CardTitle>
                        <CardDescription>
                          {menu.days} {menu.days === 1 ? 'día' : 'días'} · {menu.people}{' '}
                          {menu.people === 1 ? 'persona' : 'personas'} ·{' '}
                          {formatDateTime(menu.created_at)}
                        </CardDescription>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <span
                          className={`rounded-full border px-2.5 py-1 text-xs font-medium ${STATUS_CLASSES[menu.status]}`}
                        >
                          {MENU_STATUS_LABELS[menu.status] ?? menu.status}
                        </span>
                        <span
                          className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                            menu.price_status === 'stale'
                              ? 'border-amber-500/40 bg-amber-500/10 text-amber-900'
                              : 'border-primary/30 bg-primary/5 text-primary'
                          }`}
                        >
                          {PRICE_STATUS_LABELS[menu.price_status] ?? menu.price_status}
                        </span>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4 text-sm">
                    <dl className="grid grid-cols-2 gap-3">
                      <div>
                        <dt className="text-xs text-muted-foreground">Ticket</dt>
                        <dd className="text-lg font-semibold">{formatEuro(menu.ticket_cents)}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-muted-foreground">Presupuesto</dt>
                        <dd className="font-medium">{formatEuro(menu.budget_cents)}</dd>
                      </div>
                    </dl>

                    {menu.timed_out || menu.relaxations.length > 0 ? (
                      <p className="rounded-md bg-amber-500/10 p-2 text-xs text-amber-900">
                        {menu.timed_out ? 'Cálculo con tiempo agotado. ' : ''}
                        {menu.relaxations.length > 0
                          ? `Variedad relajada: ${menu.relaxations.length} regla(s).`
                          : ''}
                      </p>
                    ) : null}

                    <div className="flex flex-wrap gap-2">
                      <Button asChild variant="outline" size="sm">
                        <Link to={`/menus/${menu.id}`}>
                          Ver menú
                          <ArrowRight aria-hidden="true" />
                        </Link>
                      </Button>
                      <Button asChild variant="outline" size="sm">
                        <Link to={`/menus/${menu.id}/shopping-list`}>
                          <ShoppingBasket aria-hidden="true" />
                          Lista de la compra
                        </Link>
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}

      {page.total > PAGE_SIZE ? (
        <nav
          aria-label="Paginación del historial"
          className="flex flex-wrap items-center justify-between gap-3"
        >
          <p className="text-sm text-muted-foreground">
            Mostrando {page.items.length} de {page.total} menús
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!hasPrevious}
              onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
            >
              <ArrowLeft aria-hidden="true" />
              Anteriores
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!hasNext}
              onClick={() => setOffset((current) => current + PAGE_SIZE)}
            >
              Siguientes
              <ArrowRight aria-hidden="true" />
            </Button>
          </div>
        </nav>
      ) : null}

      <p className="text-xs text-muted-foreground">
        El historial no cambia si un plato se renombra o se retira del catálogo. Los precios se
        revalidan al abrir cada menú.
      </p>
    </div>
  );
}
