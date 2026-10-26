import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { renderApp } from '@/test/render-app';
import { SAMPLE_SHOPPING_LIST, server } from '@/test/server';

describe('ShoppingListPage', () => {
  it('agrupa por secciones y muestra totales, costes, despensa e identidad', async () => {
    renderApp(['/menus/1/shopping-list']);

    expect(await screen.findByRole('heading', { name: 'Lista de la compra' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Carnicería' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Arroz y pasta' })).toBeInTheDocument();

    expect(screen.getByText('Pollo')).toBeInTheDocument();
    expect(screen.getByText('Arroz redondo')).toBeInTheDocument();
    expect(screen.getByText(/1 paquete × 500 g/)).toBeInTheDocument();
    expect(screen.getByText(/1 paquete × 1000 g/)).toBeInTheDocument();

    const sticky = screen.getByRole('complementary', { name: 'Resumen fijo de la compra' });
    expect(sticky).toHaveTextContent('Total del ticket');
    expect(sticky).toHaveTextContent('5,45');
    expect(sticky).toHaveTextContent('0 de 2 productos marcados');

    expect(screen.getByText('Resumen de la compra')).toBeInTheDocument();
    expect(screen.getByText('Identidad contable')).toBeInTheDocument();
    const ticketSections = screen.getByTestId('ticket-sections-total');
    expect(ticketSections).toHaveTextContent('5,45');
    expect(ticketSections).toHaveTextContent('suma de subtotales');
    expect(screen.getByText('La lista suma exactamente el ticket.')).toBeInTheDocument();
    const identity = screen.getByTestId('accounting-identity');
    expect(identity).toHaveTextContent('5,45');
    expect(identity).toHaveTextContent('0,20');
    expect(identity).toHaveTextContent('5,44');
    expect(identity).toHaveTextContent('0,21');
    expect(screen.getByText('La identidad del menú guardado se cumple.')).toBeInTheDocument();

    const perMeal = screen.getByText('Por comida o cena').closest('div');
    expect(perMeal).toHaveTextContent('1,36');
    const perDay = screen.getByText('Por día').closest('div');
    expect(perDay).toHaveTextContent('2,73');
    const perPersonDay = screen.getByText('Por persona y día').closest('div');
    expect(perPersonDay).toHaveTextContent('1,36');

    expect(screen.getByRole('heading', { name: 'Despensa de este menú' })).toBeInTheDocument();
    expect(screen.getByText('Cebolla')).toBeInTheDocument();
    expect(screen.getByText('200 g')).toBeInTheDocument();
    expect(screen.getByText(/no a tu despensa\s+global/)).toBeInTheDocument();
  });

  it('marca y desmarca una línea y actualiza lo marcado', async () => {
    const user = userEvent.setup();
    renderApp(['/menus/1/shopping-list']);

    const checkbox = await screen.findByRole('checkbox', {
      name: 'Marcar Pollo como comprado',
    });
    await user.click(checkbox);

    expect(await screen.findByText('Producto marcado como comprado.')).toBeInTheDocument();
    const sticky = screen.getByRole('complementary', { name: 'Resumen fijo de la compra' });
    await waitFor(() => expect(sticky).toHaveTextContent('1 de 2 productos marcados'));
    expect(sticky).toHaveTextContent('4,50');
    expect(checkbox).toBeChecked();

    await user.click(checkbox);
    expect(await screen.findByText('Producto desmarcado.')).toBeInTheDocument();
    await waitFor(() => expect(sticky).toHaveTextContent('0 de 2 productos marcados'));
  });

  it('«Ya lo tengo» recalcula la lista y añade el producto a la despensa del menú', async () => {
    const user = userEvent.setup();
    renderApp(['/menus/1/shopping-list']);

    await user.click(await screen.findByRole('button', { name: 'Ya lo tengo: Pollo' }));

    expect(
      await screen.findByText(
        'Producto añadido a la despensa de este menú. No se ha modificado tu despensa global.',
      ),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.queryByRole('checkbox', { name: 'Marcar Pollo como comprado' }),
      ).not.toBeInTheDocument();
    });

    const sticky = screen.getByRole('complementary', { name: 'Resumen fijo de la compra' });
    expect(sticky).toHaveTextContent('0,95');
    expect(sticky).toHaveTextContent('0 de 1 productos marcados');

    const identity = screen.getByTestId('accounting-identity');
    expect(identity).toHaveTextContent('0,95');
    expect(identity).toHaveTextContent('4,70');
    expect(identity).toHaveTextContent('5,44');
    expect(identity).toHaveTextContent('0,21');

    expect(screen.getByRole('heading', { name: 'Despensa de este menú' })).toBeInTheDocument();
    expect(screen.getByText('Pollo')).toBeInTheDocument();
  });

  it('muestra el aviso de precios desactualizados con enlace al menú', async () => {
    server.use(
      http.get('/api/menus/:menuId/shopping-list', () =>
        HttpResponse.json({ ...SAMPLE_SHOPPING_LIST, price_status: 'stale' }),
      ),
    );
    renderApp(['/menus/1/shopping-list']);

    expect(
      await screen.findByText(/Los precios han cambiado desde que se generó el menú/),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Revalida el menú' })).toHaveAttribute(
      'href',
      '/menus/1',
    );
  });

  it('imprime la lista sin generar PDF', async () => {
    const user = userEvent.setup();
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    renderApp(['/menus/1/shopping-list']);

    await user.click(await screen.findByRole('button', { name: 'Imprimir' }));

    expect(print).toHaveBeenCalledTimes(1);
    print.mockRestore();
  });

  it('muestra la lista no encontrada', async () => {
    server.use(
      http.get('/api/menus/:menuId/shopping-list', () =>
        HttpResponse.json(
          { error: { code: 'NOT_FOUND', message: 'El menú no existe.', details: {} } },
          { status: 404 },
        ),
      ),
    );
    renderApp(['/menus/1/shopping-list']);

    expect(
      await screen.findByRole('heading', { name: 'Lista de la compra no encontrada' }),
    ).toBeInTheDocument();
  });

  it('vuelve al menú desde la cabecera', async () => {
    renderApp(['/menus/1/shopping-list']);

    expect(await screen.findByRole('link', { name: 'Volver al menú' })).toHaveAttribute(
      'href',
      '/menus/1',
    );
  });
});
