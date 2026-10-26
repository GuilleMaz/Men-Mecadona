import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

/**
 * Servidor MSW para los tests. El handler de salud permite montar el layout
 * completo sin red real; cada test puede sobrescribirlo con `server.use`.
 */
export const server = setupServer(
  http.get('/api/health', () => HttpResponse.json({ status: 'ok' })),
);
