import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { renderApp } from '@/test/render-app';
import { server } from '@/test/server';

describe('SettingsPage', () => {
  it('muestra los alérgenos y guarda el declarado', async () => {
    const user = userEvent.setup();
    let captured: unknown;
    server.use(
      http.put('/api/profile', async ({ request }) => {
        captured = await request.json();
        return HttpResponse.json({
          id: 1,
          people: 2,
          days: 7,
          budget_cents: 7000,
          allergen_codes: ['milk'],
        });
      }),
    );
    renderApp(['/settings']);

    const milk = await screen.findByLabelText('Leche');
    await user.click(milk);

    await waitFor(() => {
      expect(captured).toMatchObject({ allergen_codes: ['milk'], people: 2, days: 7 });
    });
  });

  it('añade una exclusión por ingrediente', async () => {
    const user = userEvent.setup();
    let captured: unknown;
    server.use(
      http.post('/api/exclusions', async ({ request }) => {
        captured = await request.json();
        return HttpResponse.json(
          {
            id: 4,
            kind: 'ingredient',
            ingredient_id: 2,
            dish_id: null,
            tag: null,
            label: 'Cebolla',
          },
          { status: 201 },
        );
      }),
    );
    renderApp(['/settings']);

    await screen.findByText('Exclusiones');
    const exclusionSelect = screen.getByLabelText('Ingrediente a excluir');
    await waitFor(() =>
      expect(within(exclusionSelect).getByRole('option', { name: 'Cebolla' })).toBeInTheDocument(),
    );
    await user.selectOptions(exclusionSelect, '2');
    await user.click(screen.getByRole('button', { name: 'Excluir' }));

    await waitFor(() => expect(captured).toMatchObject({ ingredient_id: 2 }));
  });

  it('añade una cantidad a la despensa en milésimas', async () => {
    const user = userEvent.setup();
    let captured: unknown;
    server.use(
      http.put('/api/pantry', async ({ request }) => {
        captured = await request.json();
        return HttpResponse.json([
          {
            id: 1,
            ingredient: {
              id: 1,
              slug: 'rice',
              name: 'Arroz',
              category: 'grains',
              group: 'carb',
              base_unit: 'g',
              grams_per_unit: null,
              protein_source: null,
              serving_group: 'carb',
              serving_size_milli: 60000,
              allergens: [],
              tags: [],
              active: true,
            },
            quantity_milli: 500000,
          },
        ]);
      }),
    );
    renderApp(['/settings']);

    await screen.findByText('Despensa');
    const pantrySelect = screen.getByLabelText('Ingrediente');
    await waitFor(() =>
      expect(within(pantrySelect).getByRole('option', { name: 'Arroz' })).toBeInTheDocument(),
    );
    await user.selectOptions(pantrySelect, '1');
    const quantity = screen.getByLabelText(/Cantidad/);
    await user.type(quantity, '500');
    await user.click(screen.getByRole('button', { name: 'Añadir' }));

    await waitFor(() => {
      expect(captured).toEqual({
        items: [{ ingredient_id: 1, quantity_milli: 500000 }],
      });
    });
  });

  it('elimina una exclusión existente', async () => {
    const user = userEvent.setup();
    const remove = vi.fn(() => new HttpResponse(null, { status: 204 }));
    server.use(
      http.get('/api/exclusions', () =>
        HttpResponse.json([
          {
            id: 7,
            kind: 'tag',
            ingredient_id: null,
            dish_id: null,
            tag: 'rice',
            label: 'rice',
          },
        ]),
      ),
      http.delete('/api/exclusions/:exclusionId', remove),
    );
    renderApp(['/settings']);

    const removeButton = await screen.findByRole('button', {
      name: 'Quitar exclusión de Arroz',
    });
    await user.click(removeButton);

    await waitFor(() => expect(remove).toHaveBeenCalledTimes(1));
  });
});
