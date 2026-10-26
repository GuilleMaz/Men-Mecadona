import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

/**
 * Servidor MSW para los tests. Los handlers por defecto permiten montar el
 * layout completo sin red real; cada test puede sobrescribirlos con `server.use`.
 */
export const server = setupServer(
  http.get('/api/health', () => HttpResponse.json({ status: 'ok' })),
  http.get('/api/catalog/status', () =>
    HttpResponse.json({
      schema_ready: true,
      is_syncing: false,
      product_count: 0,
      category_count: 0,
      food_category_count: 0,
      last_sync: null,
      last_success_at: null,
      prices_captured_at: null,
      postal_code: '22002',
      warehouse: null,
    }),
  ),
  http.post('/api/catalog/sync', () =>
    HttpResponse.json({ sync_run_id: 1, status: 'running' }, { status: 202 }),
  ),
);
