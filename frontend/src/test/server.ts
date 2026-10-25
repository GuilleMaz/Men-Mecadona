import { setupServer } from 'msw/node';

/**
 * Servidor MSW para los tests. Los handlers se añaden en cada test o en
 * `handlers.ts` cuando existan llamadas reales a la API.
 */
export const server = setupServer();
