import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router';

import App from '@/App';

/**
 * Renderiza la app con sus proveedores reales para los tests.
 *
 * @param initialEntries rutas iniciales del router en memoria.
 */
export function renderApp(initialEntries: string[] = ['/']) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
