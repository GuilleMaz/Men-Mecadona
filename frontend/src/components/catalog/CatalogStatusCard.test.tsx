import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { renderApp } from '@/test/render-app';
import { server } from '@/test/server';

import type { CatalogStatus, SyncRun } from '@/lib/catalog';

const LAST_SYNC: SyncRun = {
  id: 7,
  status: 'success',
  started_at: '2026-10-26T10:00:00+00:00',
  finished_at: '2026-10-26T10:00:08+00:00',
  postal_code: '22002',
  warehouse: '4389',
  categories_ok: 152,
  categories_failed: 0,
  categories_total: 152,
  products_seen: 4543,
  error: null,
  progress: 1,
};

function catalogStatus(overrides: Partial<CatalogStatus> = {}): CatalogStatus {
  return {
    schema_ready: true,
    is_syncing: false,
    product_count: 12345,
    category_count: 178,
    food_category_count: 150,
    last_sync: LAST_SYNC,
    last_success_at: '2026-10-26T10:00:08+00:00',
    prices_captured_at: '2026-10-26T10:00:08+00:00',
    postal_code: '22002',
    warehouse: '4389',
    last_valid_sync: LAST_SYNC,
    price_source: 'current',
    using_local_copy: false,
    fallback_reason: null,
    price_age_hours: 2,
    ...overrides,
  };
}

function mockStatus(status: CatalogStatus) {
  server.use(http.get('/api/catalog/status', () => HttpResponse.json(status)));
}

describe('CatalogStatusCard', () => {
  it('muestra el estado de la última sincronización y la tienda', async () => {
    mockStatus(catalogStatus());
    renderApp(['/settings']);

    expect(await screen.findByText('12.345')).toBeInTheDocument();
    expect(screen.getByText('Completada')).toBeInTheDocument();
    expect(screen.getByText(/CP 22002 · Almacén 4389/)).toBeInTheDocument();
    expect(screen.getByText(/152 \/ 152/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Actualizar catálogo' })).toBeEnabled();
  });

  it('muestra el estado parcial y el error de subcategorías', async () => {
    mockStatus(
      catalogStatus({
        last_sync: {
          ...LAST_SYNC,
          status: 'partial',
          categories_ok: 151,
          categories_failed: 1,
          error:
            '1 de 152 subcategorías fallaron; sus productos conservan la disponibilidad anterior.',
        },
      }),
    );
    renderApp(['/settings']);

    expect(await screen.findByText('Parcial')).toBeInTheDocument();
    expect(screen.getByText(/1 de 152 subcategorías fallaron/)).toBeInTheDocument();
    expect(screen.getByText(/1 con error/)).toBeInTheDocument();
  });

  it('muestra progreso y deshabilita el botón mientras sincroniza', async () => {
    mockStatus(
      catalogStatus({
        is_syncing: true,
        last_sync: { ...LAST_SYNC, status: 'running', progress: 0.5, finished_at: null },
      }),
    );
    renderApp(['/settings']);

    expect(await screen.findByRole('button', { name: /Sincronizando/ })).toBeDisabled();
    const progress = screen.getByRole('progressbar', { name: 'Progreso de la sincronización' });
    expect(progress).toHaveAttribute('aria-valuenow', '50');
  });

  it('lanza la sincronización al pulsar el botón', async () => {
    const user = userEvent.setup();
    mockStatus(catalogStatus());
    const post = vi.fn(() =>
      HttpResponse.json({ sync_run_id: 8, status: 'running' }, { status: 202 }),
    );
    server.use(http.post('/api/catalog/sync', post));
    renderApp(['/settings']);

    await user.click(await screen.findByRole('button', { name: 'Actualizar catálogo' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  });

  it('muestra el mensaje del backend si ya hay una sync en curso', async () => {
    const user = userEvent.setup();
    mockStatus(catalogStatus());
    server.use(
      http.post('/api/catalog/sync', () =>
        HttpResponse.json(
          {
            error: {
              code: 'SYNC_IN_PROGRESS',
              message: 'Ya hay una sincronización de catálogo en curso.',
              details: {},
            },
          },
          { status: 409 },
        ),
      ),
    );
    renderApp(['/settings']);

    await user.click(await screen.findByRole('button', { name: 'Actualizar catálogo' }));

    expect(
      await screen.findByText('Ya hay una sincronización de catálogo en curso.'),
    ).toBeInTheDocument();
  });

  it('avisa cuando se usa la última copia local válida', async () => {
    mockStatus(
      catalogStatus({
        price_source: 'local_copy',
        using_local_copy: true,
        fallback_reason: 'Mercadona no está disponible.',
        last_sync: { ...LAST_SYNC, status: 'failed', error: 'Mercadona no está disponible.' },
      }),
    );
    renderApp(['/settings']);

    expect(await screen.findByText('Usando la última copia local válida')).toBeInTheDocument();
    expect(screen.getAllByText(/Mercadona no está disponible/).length).toBeGreaterThan(0);
    expect(screen.getByText('Última copia local válida')).toBeInTheDocument();
  });

  it('avisa de que la base no está migrada y bloquea la sync', async () => {
    mockStatus(catalogStatus({ schema_ready: false, last_sync: null }));
    renderApp(['/settings']);

    expect(await screen.findByText(/La base de datos no está migrada/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Actualizar catálogo' })).toBeDisabled();
  });
});
