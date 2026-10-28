import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowLeft, Download, LoaderCircle, ShoppingBasket } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router';

import { BudgetBar } from '@/components/menu/BudgetBar';
import { ComplementDishDialog } from '@/components/menu/ComplementDishDialog';
import { ExcludeEntryDialog } from '@/components/menu/ExcludeEntryDialog';
import { MenuGrid } from '@/components/menu/MenuGrid';
import { MenuHeader } from '@/components/menu/MenuHeader';
import { RegenerateDialog } from '@/components/menu/RegenerateDialog';
import { SwapDishDialog } from '@/components/menu/SwapDishDialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DomainRequestError } from '@/lib/domain';
import {
  fetchMenu,
  menuExportUrl,
  regenerateMenu,
  removeComplement,
  revalidateMenu,
  setEntryLocked,
  type MenuDetail,
  type MenuEntry,
} from '@/lib/menu';

function toDomainError(error: unknown, fallback: string): DomainRequestError | null {
  if (!error) return null;
  if (error instanceof DomainRequestError) return error;
  return new DomainRequestError(fallback);
}

function MenuNotFound() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">Menú no encontrado</h2>
        </CardTitle>
        <CardDescription>El menú que buscas no existe o se ha eliminado.</CardDescription>
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

export function MenuDetailPage() {
  const params = useParams();
  const menuId = Number(params.id);
  const isValidId = Number.isInteger(menuId) && menuId > 0;
  const queryClient = useQueryClient();
  const [swapTarget, setSwapTarget] = useState<MenuEntry | null>(null);
  const [complementTarget, setComplementTarget] = useState<MenuEntry | null>(null);
  const [excludeTarget, setExcludeTarget] = useState<MenuEntry | null>(null);
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const autoRevalidatedFor = useRef<number | null>(null);

  const menuQuery = useQuery({
    queryKey: ['menu', menuId],
    queryFn: () => fetchMenu(menuId),
    enabled: isValidId,
    retry: false,
  });

  const applyMenu = (menu: MenuDetail) => {
    queryClient.setQueryData(['menu', menu.id], menu);
    void queryClient.invalidateQueries({ queryKey: ['menus'] });
    void queryClient.invalidateQueries({ queryKey: ['shopping-list', menu.id] });
    // Un swap o «no me gusta» puede cambiar la elegibilidad futura del catálogo
    // y, con scope=profile, las exclusiones guardadas.
    void queryClient.invalidateQueries({ queryKey: ['dishes'] });
    void queryClient.invalidateQueries({ queryKey: ['exclusions'] });
  };

  const lockMutation = useMutation({
    mutationFn: ({ entryId, locked }: { entryId: number; locked: boolean }) =>
      setEntryLocked(menuId, entryId, locked),
    onSuccess: (menu, variables) => {
      applyMenu(menu);
      setStatusMessage(
        variables.locked
          ? 'Plato bloqueado: se mantendrá al regenerar el menú.'
          : 'Plato desbloqueado: podrá cambiar al regenerar el menú.',
      );
    },
  });

  const revalidateMutation = useMutation<MenuDetail, Error, { silent?: boolean }>({
    mutationFn: () => revalidateMenu(menuId),
    onSuccess: (menu, variables) => {
      applyMenu(menu);
      if (variables.silent) return;
      setStatusMessage(
        menu.price_status === 'stale'
          ? 'Revalidación completada: los precios actuales elevan el ticket por encima del presupuesto. Se conserva el menú guardado.'
          : 'Precios revalidados: el ticket sigue dentro del presupuesto.',
      );
    },
  });

  // Al abrir un menú guardado se revalida una vez con los precios actuales.
  // Si ya estaba marcado como stale, se respeta el aviso persistido y se deja
  // que el usuario decida revalidar o regenerar.
  const revalidate = revalidateMutation.mutate;
  useEffect(() => {
    const loaded = menuQuery.data;
    if (!loaded || autoRevalidatedFor.current === loaded.id) return;
    autoRevalidatedFor.current = loaded.id;
    if (loaded.price_status !== 'current') return;
    revalidate({ silent: true });
  }, [menuQuery.data, revalidate]);

  const regenerateMutation = useMutation({
    mutationFn: async () => {
      const previousComplements = (menuQuery.data?.entries ?? []).filter(
        (entry) => entry.course === 'complement',
      ).length;
      const menu = await regenerateMenu(menuId);
      const complements = menu.entries.filter((entry) => entry.course === 'complement').length;
      return { menu, dropped: Math.max(0, previousComplements - complements) };
    },
    onSuccess: ({ menu, dropped }) => {
      applyMenu(menu);
      setRegenerateOpen(false);
      setStatusMessage(
        dropped > 0
          ? `Menú regenerado. Se descartaron ${dropped} ${dropped === 1 ? 'acompañamiento' : 'acompañamientos'} que no cabían en el presupuesto.`
          : 'Menú regenerado con tus bloqueos y preferencias.',
      );
    },
  });

  const removeComplementMutation = useMutation({
    mutationFn: (entry: MenuEntry) => removeComplement(menuId, entry.id),
    onSuccess: (menu) => {
      applyMenu(menu);
      setStatusMessage('Acompañamiento quitado. Ticket y lista recalculados.');
    },
  });

  const lockError = toDomainError(lockMutation.error, 'No se pudo cambiar el bloqueo del plato.');
  const revalidateError = toDomainError(
    revalidateMutation.error,
    'No se pudieron revalidar los precios.',
  );
  const regenerateError = toDomainError(regenerateMutation.error, 'No se pudo regenerar el menú.');
  const removeComplementError = toDomainError(
    removeComplementMutation.error,
    'No se pudo quitar el acompañamiento.',
  );

  if (!isValidId) return <MenuNotFound />;

  if (menuQuery.isPending) {
    return (
      <div className="space-y-6">
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
          Cargando menú…
        </p>
      </div>
    );
  }

  if (menuQuery.isError) {
    if (menuQuery.error instanceof DomainRequestError && menuQuery.error.code === 'NOT_FOUND') {
      return <MenuNotFound />;
    }
    return (
      <Card>
        <CardHeader>
          <CardTitle>No se pudo cargar el menú</CardTitle>
          <CardDescription>
            Comprueba que la API local esté en marcha y vuelve a intentarlo.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button type="button" variant="outline" onClick={() => void menuQuery.refetch()}>
            Reintentar
          </Button>
        </CardContent>
      </Card>
    );
  }

  const menu = menuQuery.data;
  if (!menu) return <MenuNotFound />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link to="/">
            <ArrowLeft aria-hidden="true" />
            Crear otro menú
          </Link>
        </Button>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to={`/menus/${menu.id}/shopping-list`}>
              <ShoppingBasket aria-hidden="true" />
              Lista de la compra
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <a href={menuExportUrl(menu.id, 'markdown')} download>
              <Download aria-hidden="true" />
              Markdown
            </a>
          </Button>
          <Button asChild variant="outline" size="sm">
            <a href={menuExportUrl(menu.id, 'csv')} download>
              <Download aria-hidden="true" />
              CSV
            </a>
          </Button>
        </div>
      </div>

      <MenuHeader
        menu={menu}
        isRevalidating={revalidateMutation.isPending}
        onRevalidate={() => revalidateMutation.mutate({})}
        onRegenerate={() => setRegenerateOpen(true)}
      />

      <div aria-live="polite">
        {statusMessage ? (
          <p role="status" className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
            {statusMessage}
          </p>
        ) : null}
      </div>

      {lockError ? (
        <p role="alert" className="text-sm text-destructive">
          {lockError.message}
        </p>
      ) : null}

      {removeComplementError ? (
        <p role="alert" className="text-sm text-destructive">
          {removeComplementError.message}
        </p>
      ) : null}

      {revalidateError ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
        >
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <div className="space-y-2">
            <p>{revalidateError.message}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => revalidateMutation.mutate({})}
            >
              Reintentar
            </Button>
          </div>
        </div>
      ) : null}

      <BudgetBar menu={menu} />

      {menu.entries.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Este menú no tiene comidas</CardTitle>
            <CardDescription>
              No hay entradas que mostrar. Regenera el menú para proponer comidas y cenas.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button type="button" onClick={() => setRegenerateOpen(true)}>
              Regenerar el menú
            </Button>
          </CardContent>
        </Card>
      ) : (
        <MenuGrid
          menu={menu}
          isBusy={lockMutation.isPending || removeComplementMutation.isPending}
          onToggleLock={(entry) =>
            lockMutation.mutate({ entryId: entry.id, locked: !entry.locked })
          }
          onSwap={(entry) => setSwapTarget(entry)}
          onExclude={(entry) => setExcludeTarget(entry)}
          onRegenerate={() => setRegenerateOpen(true)}
          onAddComplement={(entry) => setComplementTarget(entry)}
          onRemoveComplement={(entry) => removeComplementMutation.mutate(entry)}
        />
      )}

      <p className="text-xs text-muted-foreground">
        Precios de la tienda online de Mercadona (CP 22002, almacén 4389). Cesta no automatiza la
        compra ni sustituye al etiquetado oficial de los productos.
      </p>

      {swapTarget ? (
        <SwapDishDialog
          open
          menuId={menu.id}
          entry={swapTarget}
          onClose={() => setSwapTarget(null)}
          onSwapped={applyMenu}
        />
      ) : null}

      {complementTarget ? (
        <ComplementDishDialog
          open
          menuId={menu.id}
          entry={complementTarget}
          onClose={() => setComplementTarget(null)}
          onAdded={(updated) => {
            applyMenu(updated);
            setStatusMessage('Acompañamiento añadido. Ticket y lista recalculados.');
          }}
        />
      ) : null}

      {excludeTarget ? (
        <ExcludeEntryDialog
          open
          menuId={menu.id}
          entry={excludeTarget}
          onClose={() => setExcludeTarget(null)}
          onExcluded={applyMenu}
        />
      ) : null}

      <RegenerateDialog
        open={regenerateOpen}
        isPending={regenerateMutation.isPending}
        error={regenerateError}
        onClose={() => {
          setRegenerateOpen(false);
          regenerateMutation.reset();
        }}
        onConfirm={() => regenerateMutation.mutate()}
      />
    </div>
  );
}
