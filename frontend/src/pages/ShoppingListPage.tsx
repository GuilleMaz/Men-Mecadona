import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowLeft, Clock, LoaderCircle, Printer } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router';

import { ShoppingPantry } from '@/components/shopping/ShoppingPantry';
import { ShoppingSection } from '@/components/shopping/ShoppingSection';
import { ShoppingStickyTotal, ShoppingTotals } from '@/components/shopping/ShoppingTotals';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DomainRequestError } from '@/lib/domain';
import { formatDateTime, MENU_STATUS_LABELS, PRICE_STATUS_LABELS } from '@/lib/labels';
import {
  fetchShoppingList,
  patchShoppingItem,
  type ShoppingItem,
  type ShoppingItemPatch,
} from '@/lib/menu';

function ShoppingListNotFound() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">Lista de la compra no encontrada</h2>
        </CardTitle>
        <CardDescription>El menú no existe o su lista ya no está disponible.</CardDescription>
      </CardHeader>
      <CardContent>
        <Button asChild>
          <Link to="/">
            <ArrowLeft aria-hidden="true" />
            Crear un menú
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

export function ShoppingListPage() {
  const params = useParams();
  const menuId = Number(params.id);
  const isValidId = Number.isInteger(menuId) && menuId > 0;
  const queryClient = useQueryClient();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ['shopping-list', menuId],
    queryFn: () => fetchShoppingList(menuId),
    enabled: isValidId,
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: ({ itemId, patch }: { itemId: number; patch: ShoppingItemPatch }) =>
      patchShoppingItem(menuId, itemId, patch),
    onSuccess: (list, variables) => {
      queryClient.setQueryData(['shopping-list', menuId], list);
      void queryClient.invalidateQueries({ queryKey: ['menu', menuId] });
      void queryClient.invalidateQueries({ queryKey: ['menus'] });
      if ('already_have' in variables.patch) {
        setStatusMessage(
          'Producto añadido a la despensa de este menú. No se ha modificado tu despensa global.',
        );
      } else {
        setStatusMessage(
          variables.patch.checked ? 'Producto marcado como comprado.' : 'Producto desmarcado.',
        );
      }
    },
  });

  if (!isValidId) return <ShoppingListNotFound />;

  if (listQuery.isPending) {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
        Cargando lista de la compra…
      </p>
    );
  }

  if (listQuery.isError) {
    if (listQuery.error instanceof DomainRequestError && listQuery.error.code === 'NOT_FOUND') {
      return <ShoppingListNotFound />;
    }
    return (
      <Card>
        <CardHeader>
          <CardTitle>No se pudo cargar la lista de la compra</CardTitle>
          <CardDescription>
            Comprueba que la API local esté en marcha y vuelve a intentarlo.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button type="button" variant="outline" onClick={() => void listQuery.refetch()}>
            Reintentar
          </Button>
        </CardContent>
      </Card>
    );
  }

  const list = listQuery.data;
  if (!list) return <ShoppingListNotFound />;

  const pendingItemId = mutation.isPending ? (mutation.variables?.itemId ?? null) : null;
  const apiError =
    mutation.error instanceof DomainRequestError
      ? mutation.error
      : mutation.error
        ? new DomainRequestError('No se pudo actualizar la lista de la compra.')
        : null;
  const itemCount = list.sections.reduce((count, section) => count + section.items.length, 0);

  return (
    <div className="space-y-6 pb-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link to={`/menus/${menuId}`}>
            <ArrowLeft aria-hidden="true" />
            Volver al menú
          </Link>
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => window.print()}>
          <Printer aria-hidden="true" />
          Imprimir
        </Button>
      </div>

      <div className="space-y-2">
        <h2 className="text-2xl font-semibold">Lista de la compra</h2>
        <p className="text-sm text-muted-foreground">
          Menú de {list.days} {list.days === 1 ? 'día' : 'días'} para {list.people}{' '}
          {list.people === 1 ? 'persona' : 'personas'}. Agrupada por secciones, con paquetes
          cerrados y precios de Mercadona online.
        </p>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-full border bg-muted px-2.5 py-1 font-medium">
            {MENU_STATUS_LABELS[list.status] ?? list.status}
          </span>
          <span
            className={`rounded-full border px-2.5 py-1 font-medium ${
              list.price_status === 'stale'
                ? 'border-amber-500/40 bg-amber-500/10 text-amber-900'
                : 'border-primary/30 bg-primary/5 text-primary'
            }`}
          >
            {PRICE_STATUS_LABELS[list.price_status] ?? list.price_status}
          </span>
          {list.timed_out ? (
            <span className="flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 font-medium text-amber-900">
              <Clock aria-hidden="true" className="size-3.5" />
              Tiempo de cálculo agotado
            </span>
          ) : null}
          <span className="rounded-full border px-2.5 py-1 text-muted-foreground">
            CP {list.postal_code} · Almacén {list.warehouse} · Precios:{' '}
            {formatDateTime(list.prices_captured_at)}
          </span>
        </div>
      </div>

      {list.price_status === 'stale' ? (
        <div
          role="status"
          className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-900"
        >
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <p>
            Los precios han cambiado desde que se generó el menú. La lista conserva el ticket
            guardado.{' '}
            <Link to={`/menus/${menuId}`} className="underline underline-offset-4">
              Revalida el menú
            </Link>{' '}
            para actualizarlo.
          </p>
        </div>
      ) : null}

      <div aria-live="polite">
        {statusMessage ? (
          <p role="status" className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
            {statusMessage}
          </p>
        ) : null}
      </div>

      {apiError ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
        >
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <div className="space-y-2">
            <p>{apiError.message}</p>
            {apiError.code === 'BUDGET_EXCEEDED' ? (
              <p className="text-xs">
                «Ya lo tengo» reduciría la compra, pero los precios actuales no permiten mantener el
                menú dentro del presupuesto. Revalida o regenera el menú.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      {itemCount === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>No hace falta comprar nada</CardTitle>
            <CardDescription>
              La despensa cubre todos los ingredientes de este menú. Puedes revisar el menú o
              regenerarlo.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild variant="outline">
              <Link to={`/menus/${menuId}`}>Volver al menú</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {list.sections.map((section) => (
            <ShoppingSection
              key={`${section.section_id ?? 'none'}-${section.section_name}`}
              section={section}
              pendingItemId={pendingItemId}
              onToggleChecked={(item: ShoppingItem, checked: boolean) =>
                mutation.mutate({ itemId: item.id, patch: { checked } })
              }
              onAlreadyHave={(item: ShoppingItem) =>
                mutation.mutate({ itemId: item.id, patch: { already_have: true } })
              }
            />
          ))}
        </div>
      )}

      <ShoppingTotals list={list} />

      <ShoppingPantry items={list.pantry_items} />

      <ShoppingStickyTotal list={list} />

      <p className="text-xs text-muted-foreground">
        Precios de la tienda online de Mercadona (CP 22002, almacén 4389). Cesta no automatiza la
        compra: la lista se lleva al supermercado o se imprime. Confirma siempre el etiquetado y los
        alérgenos en el envase.
      </p>
    </div>
  );
}
