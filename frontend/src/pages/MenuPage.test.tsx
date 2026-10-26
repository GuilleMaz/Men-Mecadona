import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderApp } from '@/test/render-app';
import { server } from '@/test/server';

describe('MenuPage', () => {
  it('acepta un menú válido y muestra el resumen', async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole('button', { name: 'Generar menú' }));

    const status = await screen.findByRole('status', { name: 'Resumen del menú' });
    expect(status).toHaveTextContent('2 personas · 7 días · 70,00');
    expect(status).toHaveTextContent('de presupuesto');
  });

  it('guarda el perfil con el presupuesto en céntimos', async () => {
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

  it('rechaza cero días con un mensaje en español', async () => {
    const user = userEvent.setup();
    renderApp();

    const days = screen.getByLabelText('Días');
    await user.clear(days);
    await user.type(days, '0');
    await user.click(screen.getByRole('button', { name: 'Generar menú' }));

    expect(await screen.findByText('El menú debe cubrir al menos 1 día.')).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Resumen del menú' })).not.toBeInTheDocument();
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
