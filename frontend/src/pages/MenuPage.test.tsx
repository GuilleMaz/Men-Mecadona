import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { renderApp } from '@/test/render-app';
import { server } from '@/test/server';

describe('MenuPage', () => {
  it('genera el menú y navega al detalle persistido', async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole('button', { name: 'Generar menú' }));

    expect(
      await screen.findByRole('heading', { name: 'Menú de 7 días para 2 personas' }),
    ).toBeInTheDocument();
    expect(screen.getAllByText('Pollo con arroz').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: 'Lista de la compra' })).toBeInTheDocument();
  });

  it('guarda el perfil con el presupuesto en céntimos antes de generar', async () => {
    const user = userEvent.setup();
    let captured: unknown;
    server.use(
      http.put('/api/profile', async ({ request }) => {
        captured = await request.json();
        return HttpResponse.json({
          id: 1,
          people: 2,
          days: 7,
          budget_cents: 8550,
          allergen_codes: [],
        });
      }),
    );
    renderApp();

    const budget = screen.getByLabelText('Presupuesto total (€)');
    await user.clear(budget);
    await user.type(budget, '85.50');
    await user.click(screen.getByRole('button', { name: 'Generar menú' }));

    await waitFor(() => {
      expect(captured).toMatchObject({
        people: 2,
        days: 7,
        budget_cents: 8550,
      });
    });
  });

  it('muestra el mínimo, el déficit y las sugerencias si es inviable', async () => {
    const user = userEvent.setup();
    const generate = vi.fn(() =>
      HttpResponse.json({
        status: 'infeasible',
        is_preview: true,
        reason: 'budget',
        menu_id: null,
        people: 2,
        days: 7,
        budget_cents: 7000,
        ticket_cents: null,
        consumption_cents: null,
        pantry_consumption_cents: null,
        leftover_value_cents: null,
        minimum_ticket_cents: 12000,
        minimum_is_estimate: true,
        shortfall_cents: 5000,
        relaxations: [],
        suggestions: [
          'Aumenta el presupuesto al menos 50,00 €.',
          'Reduce los días o el número de personas.',
        ],
        price_status: null,
        timed_out: false,
        postal_code: '22002',
        warehouse: '4389',
        prices_captured_at: '2026-10-26T08:00:00Z',
        entries: [],
      }),
    );
    server.use(http.post('/api/menus/generate', generate));
    renderApp();

    await user.click(screen.getByRole('button', { name: 'Generar menú' }));

    const dialog = await screen.findByRole('dialog', {
      name: 'El menú no cabe en el presupuesto',
    });
    expect(dialog).toHaveTextContent('Mínimo estimado');
    expect(dialog).toHaveTextContent('120,00');
    expect(dialog).toHaveTextContent('Déficit');
    expect(dialog).toHaveTextContent('50,00');
    expect(dialog).toHaveTextContent('Aumenta el presupuesto al menos 50,00 €.');
    expect(dialog).toHaveTextContent('Reduce los días o el número de personas.');
    expect(dialog).toHaveTextContent('No se ha guardado ningún menú');
    expect(screen.queryByRole('heading', { name: /^Menú de/ })).not.toBeInTheDocument();
    expect(generate).toHaveBeenCalledTimes(1);
  });

  it('muestra un error accesible y permite reintentar', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.post('/api/menus/generate', () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json(
            {
              error: {
                code: 'NO_ELIGIBLE_DISHES',
                message: 'No hay platos elegibles con tus preferencias.',
                details: {},
              },
            },
            { status: 422 },
          );
        }
        return HttpResponse.json({
          status: 'feasible',
          is_preview: false,
          reason: null,
          menu_id: 1,
          people: 2,
          days: 7,
          budget_cents: 7000,
          ticket_cents: 545,
          consumption_cents: 544,
          pantry_consumption_cents: 20,
          leftover_value_cents: 21,
          minimum_ticket_cents: null,
          minimum_is_estimate: false,
          shortfall_cents: 0,
          relaxations: [],
          suggestions: [],
          price_status: 'current',
          timed_out: false,
          postal_code: '22002',
          warehouse: '4389',
          prices_captured_at: '2026-10-26T08:00:00Z',
          entries: [],
        });
      }),
    );
    renderApp();

    await user.click(screen.getByRole('button', { name: 'Generar menú' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('No hay platos elegibles con tus preferencias.');
    expect(alert).toHaveTextContent('Revisa tus alérgenos, exclusiones y la despensa');

    await user.click(screen.getByRole('button', { name: 'Reintentar' }));

    expect(await screen.findByRole('heading', { name: /^Menú de/ })).toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it('avisa cuando el optimizador agota el tiempo sin menú', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/menus/generate', () =>
        HttpResponse.json({
          status: 'timeout',
          is_preview: false,
          reason: 'timeout',
          menu_id: null,
          people: 2,
          days: 7,
          budget_cents: 7000,
          ticket_cents: null,
          consumption_cents: null,
          pantry_consumption_cents: null,
          leftover_value_cents: null,
          minimum_ticket_cents: null,
          minimum_is_estimate: false,
          shortfall_cents: 0,
          relaxations: [],
          suggestions: [],
          price_status: null,
          timed_out: true,
          postal_code: '22002',
          warehouse: '4389',
          prices_captured_at: '2026-10-26T08:00:00Z',
          entries: [],
        }),
      ),
    );
    renderApp();

    await user.click(screen.getByRole('button', { name: 'Generar menú' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('No se generó ningún menú');
    expect(alert).toHaveTextContent('El cálculo agotó el tiempo disponible');
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /^Menú de/ })).not.toBeInTheDocument();
  });

  it('muestra el estado generando y deshabilita el botón', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/menus/generate', async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return HttpResponse.json({
          status: 'timeout',
          is_preview: false,
          reason: 'timeout',
          menu_id: null,
          people: 2,
          days: 7,
          budget_cents: 7000,
          ticket_cents: null,
          consumption_cents: null,
          pantry_consumption_cents: null,
          leftover_value_cents: null,
          minimum_ticket_cents: null,
          minimum_is_estimate: false,
          shortfall_cents: 0,
          relaxations: [],
          suggestions: [],
          price_status: null,
          timed_out: true,
          postal_code: '22002',
          warehouse: '4389',
          prices_captured_at: '2026-10-26T08:00:00Z',
          entries: [],
        });
      }),
    );
    renderApp();

    await user.click(screen.getByRole('button', { name: 'Generar menú' }));

    expect(
      await screen.findByText('Generando comidas y cenas dentro de tu presupuesto…'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Generando menú…' })).toBeDisabled();

    expect(await screen.findByText('No se generó ningún menú')).toBeInTheDocument();
  });

  it('rechaza cero días con un mensaje en español', async () => {
    const user = userEvent.setup();
    renderApp();

    const days = screen.getByLabelText('Días');
    await user.clear(days);
    await user.type(days, '0');
    await user.click(screen.getByRole('button', { name: 'Generar menú' }));

    expect(await screen.findByText('El menú debe cubrir al menos 1 día.')).toBeInTheDocument();
  });

  it('rechaza más de 10 personas', async () => {
    const user = userEvent.setup();
    renderApp();

    const people = screen.getByLabelText('Personas');
    await user.clear(people);
    await user.type(people, '11');
    await user.click(screen.getByRole('button', { name: 'Generar menú' }));

    expect(await screen.findByText('El máximo es 10 personas.')).toBeInTheDocument();
  });
});
