import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  CircleAlert,
  CircleCheck,
  Database,
  LoaderCircle,
  RefreshCw,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  CatalogRequestError,
  fetchCatalogStatus,
  startCatalogSync,
  type CatalogStatus,
  type SyncStatus,
} from '@/lib/catalog';

const numberFormatter = new Intl.NumberFormat('es-ES');
const dateFormatter = new Intl.DateTimeFormat('es-ES', {
  dateStyle: 'short',
  timeStyle: 'short',
});

const statusLabels: Record<SyncStatus, string> = {
  running: 'En curso',
  success: 'Completada',
  partial: 'Parcial',
  failed: 'Fallida',
};

const statusClasses: Record<SyncStatus, string> = {
  running: 'border-primary/30 bg-primary/5 text-primary',
  success: 'border-primary/30 bg-primary/5 text-primary',
  partial: 'border-amber-500/40 bg-amber-500/10 text-amber-700',
  failed: 'border-destructive/30 bg-destructive/5 text-destructive',
};

function formatDate(value: string | null): string {
  if (!value) {
    return '—';
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : dateFormatter.format(date);
}

function SyncBadge({ status, isSyncing }: { status: SyncStatus | null; isSyncing: boolean }) {
  const effective = isSyncing ? 'running' : status;
  if (!effective) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
        <CircleAlert aria-hidden="true" className="size-3.5" />
        Sin sincronizar
      </span>
    );
  }
  const Icon =
    effective === 'running' ? LoaderCircle : effective === 'failed' ? CircleAlert : CircleCheck;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${statusClasses[effective]}`}
    >
      <Icon
        aria-hidden="true"
        className={`size-3.5 ${effective === 'running' ? 'animate-spin' : ''}`}
      />
      {statusLabels[effective]}
    </span>
  );
}

function StatusDetails({ data }: { data: CatalogStatus }) {
  const lastSync = data.last_sync;
  const completed = lastSync ? lastSync.categories_ok + lastSync.categories_failed : 0;
  const priceSourceLabels = {
    current: 'Precios actuales',
    local_copy: 'Última copia local válida',
    unavailable: 'Sin copia válida',
  } as const;

  return (
    <div className="grid gap-3 text-sm sm:grid-cols-2">
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">Productos</p>
        <p className="font-medium">{numberFormatter.format(data.product_count)}</p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">Categorías</p>
        <p className="font-medium">
          {numberFormatter.format(data.category_count)} (
          {numberFormatter.format(data.food_category_count)} de comida)
        </p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">
          Última sincronización
        </p>
        <p className="font-medium">{formatDate(lastSync?.started_at ?? null)}</p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">Subcategorías</p>
        <p className="font-medium">
          {lastSync
            ? `${numberFormatter.format(completed)} / ${numberFormatter.format(lastSync.categories_total)}`
            : '—'}
          {lastSync && lastSync.categories_failed > 0
            ? ` · ${numberFormatter.format(lastSync.categories_failed)} con error`
            : ''}
        </p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">Precios capturados</p>
        <p className="font-medium">{formatDate(data.prices_captured_at)}</p>
        {data.price_age_hours !== null ? (
          <p className="text-xs text-muted-foreground">
            Hace {numberFormatter.format(data.price_age_hours)} h
          </p>
        ) : null}
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">Tienda</p>
        <p className="font-medium">
          CP {data.postal_code} · Almacén {data.warehouse ?? 'sin confirmar'}
        </p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">Origen de precios</p>
        <p className="font-medium">{priceSourceLabels[data.price_source]}</p>
      </div>
    </div>
  );
}

/** Estado del catálogo de Mercadona y botón de actualización. */
export function CatalogStatusCard() {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ['catalog', 'status'],
    queryFn: fetchCatalogStatus,
    refetchInterval: (query) => (query.state.data?.is_syncing ? 2000 : false),
  });
  const syncMutation = useMutation({
    mutationFn: startCatalogSync,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['catalog', 'status'] });
    },
  });

  const data = statusQuery.data;
  const isSyncing = data?.is_syncing ?? false;
  const actionError =
    syncMutation.error instanceof CatalogRequestError
      ? syncMutation.error.message
      : syncMutation.error
        ? 'No se pudo iniciar la sincronización.'
        : null;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2">
              <Database aria-hidden="true" className="size-5 text-primary" />
              Catálogo de Mercadona
            </CardTitle>
            <CardDescription>
              Precios de la tienda online para CP 22002. Una sync parcial no oculta los productos de
              las subcategorías que sí se descargaron.
            </CardDescription>
          </div>
          <SyncBadge status={data?.last_sync?.status ?? null} isSyncing={isSyncing} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {statusQuery.isPending ? (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
            Consultando el estado del catálogo…
          </p>
        ) : null}

        {statusQuery.isError ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
          >
            <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <div className="space-y-2">
              <p>No se pudo consultar el estado del catálogo.</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void statusQuery.refetch()}
              >
                Reintentar
              </Button>
            </div>
          </div>
        ) : null}

        {data ? (
          <>
            <div aria-live="polite">
              <StatusDetails data={data} />
            </div>

            {!data.schema_ready ? (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-800"
              >
                <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                <p>
                  La base de datos no está migrada. Ejecuta{' '}
                  <code className="rounded bg-muted px-1 py-0.5 text-xs">
                    uv run alembic upgrade head
                  </code>{' '}
                  desde <code className="rounded bg-muted px-1 py-0.5 text-xs">backend</code> y
                  vuelve a cargar esta pantalla.
                </p>
              </div>
            ) : null}

            {data.schema_ready && data.product_count === 0 ? (
              <p className="text-sm text-muted-foreground">
                El catálogo está vacío. Pulsa «Actualizar catálogo» para descargarlo.
              </p>
            ) : null}

            {data.price_source === 'local_copy' ? (
              <div
                role="status"
                className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-900"
              >
                <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                <div className="space-y-1">
                  <p className="font-medium">Usando la última copia local válida</p>
                  <p>
                    {data.fallback_reason ??
                      'La última sincronización no terminó; se conservan los precios anteriores.'}{' '}
                    Puedes consultar y revalidar menús guardados, pero no se generarán menús nuevos
                    hasta que una sincronización confirme el CP 22002 y el almacén 4389.
                  </p>
                </div>
              </div>
            ) : null}

            {data.price_source === 'unavailable' && data.product_count > 0 ? (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
              >
                <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                <p>
                  {data.fallback_reason ??
                    'No hay una copia de precios válida del CP 22002 y el almacén 4389.'}{' '}
                  No se generarán menús nuevos con esta copia.
                </p>
              </div>
            ) : null}

            {isSyncing && data.last_sync ? (
              <div className="space-y-1">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Descargando catálogo…</span>
                  <span>{Math.round(data.last_sync.progress * 100)} %</span>
                </div>
                <div
                  role="progressbar"
                  aria-label="Progreso de la sincronización"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(data.last_sync.progress * 100)}
                  className="h-2 overflow-hidden rounded-full bg-muted"
                >
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${Math.round(data.last_sync.progress * 100)}%` }}
                  />
                </div>
              </div>
            ) : null}

            {data.last_sync?.error ? (
              <p
                role="alert"
                className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-800"
              >
                {data.last_sync.error}
              </p>
            ) : null}
          </>
        ) : null}

        {actionError ? (
          <p role="alert" className="text-sm text-destructive">
            {actionError}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            onClick={() => syncMutation.mutate()}
            disabled={isSyncing || syncMutation.isPending || data?.schema_ready === false}
          >
            <RefreshCw
              aria-hidden="true"
              className={`size-4 ${isSyncing || syncMutation.isPending ? 'animate-spin' : ''}`}
            />
            {isSyncing ? 'Sincronizando…' : 'Actualizar catálogo'}
          </Button>
          <p className="text-xs text-muted-foreground">
            La descarga se ejecuta en segundo plano; puedes seguir usando la app.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
