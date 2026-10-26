import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { resetMenuFixture, server } from './server';

// Sin red real: cualquier petición no declarada se considera un error.
beforeAll(() => server.listen({ onUnhandledFrame: 'error' }));

afterEach(() => {
  cleanup();
  server.resetHandlers();
  resetMenuFixture();
});

afterAll(() => server.close());
