import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { renderApp } from '@/test/render-app';
import { server } from '@/test/server';

describe('DishesPage', () => {
  it('muestra el catálogo y abre la composición del plato', async () => {
    const user = userEvent.setup();
    renderApp(['/dishes']);

    expect(await screen.findByRole('heading', { name: 'Catálogo de platos' })).toBeInTheDocument();
    expect(await screen.findByText('Pollo con arroz')).toBeInTheDocument();
    expect(screen.getByText(/1 platos encontrados/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Ver ingredientes' }));

    expect(await screen.findByText('Pollo')).toBeInTheDocument();
    expect(screen.getByText(/300 g para 2 raciones/)).toBeInTheDocument();
  });

  it('muestra el coste del plato con las personas del perfil', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/profile', () =>
        HttpResponse.json({
          id: 1,
          people: 4,
          days: 7,
          budget_cents: 9000,
          allergen_codes: [],
        }),
      ),
    );
    renderApp(['/dishes']);

    await user.click(await screen.findByRole('button', { name: 'Ver ingredientes' }));

    expect(await screen.findByText('Coste del plato')).toBeInTheDocument();
    // 144 céntimos por ración × 4 personas = 5,76 € de consumo.
    expect(await screen.findByText(/5,76/)).toBeInTheDocument();
    expect(screen.getByText(/por ración/)).toBeInTheDocument();
    expect(screen.getByText('Compra estimada')).toBeInTheDocument();
  });

  it('envía la exclusión de un plato', async () => {
    const user = userEvent.setup();
    const post = vi.fn(async ({ request }: { request: Request }) => {
      const body = (await request.json()) as { dish_id?: number };
      return HttpResponse.json(
        {
          id: 9,
          kind: 'dish',
          ingredient_id: null,
          dish_id: body.dish_id ?? 1,
          tag: null,
          label: 'Pollo con arroz',
        },
        { status: 201 },
      );
    });
    server.use(http.post('/api/exclusions', post));
    renderApp(['/dishes']);

    await user.click(await screen.findByRole('button', { name: 'No me gusta' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  });

  it('envía la exclusión de un ingrediente desde el detalle', async () => {
    const user = userEvent.setup();
    let capturedIngredientId: number | undefined;
    server.use(
      http.post('/api/exclusions', async ({ request }) => {
        const body = (await request.json()) as { ingredient_id?: number };
        capturedIngredientId = body.ingredient_id;
        return HttpResponse.json(
          {
            id: 10,
            kind: 'ingredient',
            ingredient_id: body.ingredient_id ?? 1,
            dish_id: null,
            tag: null,
            label: 'Pollo',
          },
          { status: 201 },
        );
      }),
    );
    renderApp(['/dishes']);

    await user.click(await screen.findByRole('button', { name: 'Ver ingredientes' }));
    await user.click(screen.getAllByRole('button', { name: 'No me gusta este ingrediente' })[0]!);

    await waitFor(() => expect(capturedIngredientId).toBe(3));
  });

  it('envía el filtro de cena a la API', async () => {
    const user = userEvent.setup();
    const urls: string[] = [];
    server.use(
      http.get('/api/dishes', ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({ items: [], total: 0, limit: 100, offset: 0 });
      }),
    );
    renderApp(['/dishes']);

    await screen.findByText('No hay platos que coincidan con los filtros.');
    await user.selectOptions(screen.getByLabelText('Momento'), 'dinner');

    await waitFor(() => {
      expect(urls.some((url) => url.includes('meal_type=dinner'))).toBe(true);
    });
  });

  it('envía el filtro de curso a la API', async () => {
    const user = userEvent.setup();
    const urls: string[] = [];
    server.use(
      http.get('/api/dishes', ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({ items: [], total: 0, limit: 100, offset: 0 });
      }),
    );
    renderApp(['/dishes']);

    await screen.findByText('No hay platos que coincidan con los filtros.');
    await user.selectOptions(screen.getByLabelText('Curso'), 'complement');

    await waitFor(() => {
      expect(urls.some((url) => url.includes('role=complement'))).toBe(true);
    });
  });

  it('muestra el estado vacío si no hay platos elegibles', async () => {
    server.use(
      http.get('/api/dishes', () =>
        HttpResponse.json({ items: [], total: 0, limit: 100, offset: 0 }),
      ),
    );
    renderApp(['/dishes']);

    expect(
      await screen.findByText('No hay platos que coincidan con los filtros.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Prueba a mostrar los no elegibles o revisa tus exclusiones/),
    ).toBeInTheDocument();
  });
});
