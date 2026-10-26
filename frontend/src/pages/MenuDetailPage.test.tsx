import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderApp } from '@/test/render-app';
import { SAMPLE_MENU, server } from '@/test/server';

describe('MenuDetailPage', () => {
  it('muestra la rejilla de días, la cabecera y la barra de presupuesto', async () => {
    renderApp(['/menus/1']);

    expect(
      await screen.findByRole('heading', { name: 'Menú de 2 días para 2 personas' }),
    ).toBeInTheDocument();

    expect(screen.getByRole('heading', { name: 'Día 1' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Día 2' })).toBeInTheDocument();
    expect(screen.getAllByText('Comida')).toHaveLength(2);
    expect(screen.getAllByText('Cena')).toHaveLength(2);

    expect(screen.getByText('Pollo con arroz')).toBeInTheDocument();
    expect(screen.getByText('Tortilla de patatas')).toBeInTheDocument();
    expect(screen.getByText('Lentejas guisadas')).toBeInTheDocument();
    expect(screen.getByText('Sopa de verduras')).toBeInTheDocument();

    const progress = screen.getByRole('progressbar', { name: 'Presupuesto usado' });
    expect(progress).toHaveAttribute('aria-valuenow', '545');
    expect(progress).toHaveAttribute('aria-valuemax', '7000');
    expect(screen.getByText(/de 70,00/)).toBeInTheDocument();
    expect(screen.getByText('Consumo')).toBeInTheDocument();
    expect(screen.getByText('Despensa')).toBeInTheDocument();
    expect(screen.getByText('Sobras')).toBeInTheDocument();

    expect(screen.getByText('22002')).toBeInTheDocument();
    expect(screen.getByText('4389')).toBeInTheDocument();
    expect(screen.getByText('Fecha de los precios')).toBeInTheDocument();
    expect(screen.getByText('Factible')).toBeInTheDocument();
  });

  it('bloquea y desbloquea una entrada', async () => {
    const user = userEvent.setup();
    renderApp(['/menus/1']);

    await user.click(await screen.findByRole('button', { name: 'Bloquear Pollo con arroz' }));

    expect(
      await screen.findByRole('button', { name: 'Desbloquear Pollo con arroz' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Plato bloqueado/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Desbloquear Pollo con arroz' }));

    expect(
      await screen.findByRole('button', { name: 'Bloquear Pollo con arroz' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Plato desbloqueado/)).toBeInTheDocument();
  });

  it('cambia un plato por otro elegible del hueco', async () => {
    const user = userEvent.setup();
    renderApp(['/menus/1']);

    await user.click(await screen.findByRole('button', { name: 'Cambiar Tortilla de patatas' }));

    const dialog = await screen.findByRole('dialog', { name: 'Cambiar cena' });
    const option = await within(dialog).findByRole('radio', { name: /Sopa de verduras/ });
    await user.click(option);
    await user.click(within(dialog).getByRole('button', { name: 'Cambiar plato' }));

    await waitFor(() => {
      expect(screen.queryByText('Tortilla de patatas')).not.toBeInTheDocument();
    });
    expect(screen.getAllByText('Sopa de verduras')).toHaveLength(2);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('carga los platos elegibles del hueco con los filtros del contrato', async () => {
    const user = userEvent.setup();
    const urls: string[] = [];
    server.use(
      http.get('/api/dishes', ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({ items: [], total: 0, limit: 100, offset: 0 });
      }),
    );
    renderApp(['/menus/1']);

    await user.click(await screen.findByRole('button', { name: 'Cambiar Tortilla de patatas' }));

    const dialog = await screen.findByRole('dialog', { name: 'Cambiar cena' });
    expect(
      await within(dialog).findByText(/No hay otros platos elegibles para este hueco/),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        urls.some(
          (url) =>
            url.includes('meal_type=dinner') &&
            url.includes('only_eligible=true') &&
            url.includes('limit=100'),
        ),
      ).toBe(true);
    });
  });

  it('rechaza un cambio que supera el presupuesto sin tocar el menú', async () => {
    const user = userEvent.setup();
    renderApp(['/menus/1']);

    await user.click(await screen.findByRole('button', { name: 'Cambiar Tortilla de patatas' }));

    const dialog = await screen.findByRole('dialog', { name: 'Cambiar cena' });
    await user.click(await within(dialog).findByRole('radio', { name: /Solomillo con patatas/ }));
    await user.click(within(dialog).getByRole('button', { name: 'Cambiar plato' }));

    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('El cambio supera el presupuesto y no se ha aplicado.');
    expect(alert).toHaveTextContent('Prueba con otro plato');
    expect(screen.getByText('Tortilla de patatas')).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Cambiar cena' })).toBeInTheDocument();
  });

  it('registra «no me gusta» con alcance de perfil y cambia el plato', async () => {
    const user = userEvent.setup();
    let captured: unknown;
    server.use(
      http.post('/api/menus/:menuId/entries/:entryId/exclude', async ({ request }) => {
        captured = await request.json();
        return HttpResponse.json(SAMPLE_MENU);
      }),
    );
    renderApp(['/menus/1']);

    await user.click(
      await screen.findByRole('button', { name: 'No me gusta Tortilla de patatas' }),
    );

    const dialog = await screen.findByRole('dialog', {
      name: 'No me gusta «Tortilla de patatas»',
    });
    await user.click(within(dialog).getByRole('radio', { name: /En este menú y en los futuros/ }));
    await user.click(within(dialog).getByRole('button', { name: 'No me gusta' }));

    await waitFor(() => {
      expect(captured).toEqual({ scope: 'profile' });
    });
  });

  it('revalida los precios una vez al abrir un menú guardado actual', async () => {
    let revalidations = 0;
    server.use(
      http.post('/api/menus/:menuId/revalidate', () => {
        revalidations += 1;
        return HttpResponse.json(SAMPLE_MENU);
      }),
    );
    renderApp(['/menus/1']);

    expect(
      await screen.findByRole('heading', { name: 'Menú de 2 días para 2 personas' }),
    ).toBeInTheDocument();
    await waitFor(() => expect(revalidations).toBe(1));
    expect(screen.queryByText(/Precios revalidados/)).not.toBeInTheDocument();
  });

  it('muestra el banner stale y permite revalidar', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/menus/:menuId', () =>
        HttpResponse.json({
          ...SAMPLE_MENU,
          price_status: 'stale',
          previous_ticket_cents: 545,
          revalidated_ticket_cents: 7200,
          price_delta_cents: 6655,
          revalidated_at: '2026-10-26T10:00:00Z',
        }),
      ),
    );
    renderApp(['/menus/1']);

    expect(
      await screen.findByText('Los precios han cambiado desde que se generó el menú'),
    ).toBeInTheDocument();
    expect(screen.getByText(/Ticket revalidado/)).toHaveTextContent('72,00');
    expect(screen.getByText(/diferencia \+66,55/)).toBeInTheDocument();
    expect(screen.getByText('Precios desactualizados')).toBeInTheDocument();
    expect(
      screen.getByText(/Los precios actuales elevan el ticket por encima del presupuesto/),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Revalidar precios' }));

    await waitFor(() => {
      expect(
        screen.queryByText('Los precios han cambiado desde que se generó el menú'),
      ).not.toBeInTheDocument();
    });
    expect(await screen.findByText(/Precios revalidados/)).toBeInTheDocument();
  });

  it('avisa cuando el ticket está cerca del límite del presupuesto', async () => {
    const nearLimit = { ...SAMPLE_MENU, budget_cents: 560 };
    server.use(
      http.get('/api/menus/:menuId', () => HttpResponse.json(nearLimit)),
      http.post('/api/menus/:menuId/revalidate', () => HttpResponse.json(nearLimit)),
    );
    renderApp(['/menus/1']);

    expect(await screen.findByText(/Estás cerca del límite del presupuesto/)).toBeInTheDocument();
  });

  it('muestra los estados relajado y con tiempo agotado', async () => {
    const relaxed = {
      ...SAMPLE_MENU,
      status: 'relaxed' as const,
      timed_out: true,
      relaxations: ['protein_sources', 'fish'],
    };
    server.use(
      http.get('/api/menus/:menuId', () => HttpResponse.json(relaxed)),
      http.post('/api/menus/:menuId/revalidate', () => HttpResponse.json(relaxed)),
    );
    renderApp(['/menus/1']);

    expect(await screen.findByText('Relajado')).toBeInTheDocument();
    expect(screen.getAllByText('Tiempo de cálculo agotado').length).toBeGreaterThan(0);
    expect(screen.getByText('Falta variedad de proteínas')).toBeInTheDocument();
    expect(screen.getByText('Menos pescado del recomendado')).toBeInTheDocument();
  });

  it('regenera el menú tras confirmar', async () => {
    const user = userEvent.setup();
    renderApp(['/menus/1']);

    await user.click(await screen.findByRole('button', { name: 'Regenerar menú' }));

    const dialog = await screen.findByRole('dialog', { name: 'Regenerar el menú' });
    await user.click(within(dialog).getByRole('button', { name: 'Confirmar regeneración' }));

    expect(
      await screen.findByText('Menú regenerado con tus bloqueos y preferencias.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('muestra la página de menú no encontrado', async () => {
    server.use(
      http.get('/api/menus/:menuId', () =>
        HttpResponse.json(
          { error: { code: 'NOT_FOUND', message: 'El menú no existe.', details: {} } },
          { status: 404 },
        ),
      ),
    );
    renderApp(['/menus/999']);

    expect(await screen.findByRole('heading', { name: 'Menú no encontrado' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Crear un menú' })).toBeInTheDocument();
  });
});
