import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderApp } from '@/test/render-app';
import { server } from '@/test/server';

describe('HistoryPage', () => {
  it('lista los menús guardados con su ticket y enlaces', async () => {
    renderApp(['/history']);

    expect(await screen.findByRole('heading', { name: 'Historial de menús' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Menú #1' })).toBeInTheDocument();
    expect(screen.getByText(/5,45/)).toBeInTheDocument();
    expect(screen.getByText(/70,00/)).toBeInTheDocument();
    expect(screen.getByText('Factible')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Ver menú/ })).toHaveAttribute('href', '/menus/1');
    expect(screen.getByRole('link', { name: 'Lista de la compra' })).toHaveAttribute(
      'href',
      '/menus/1/shopping-list',
    );
  });

  it('muestra el estado vacío sin menús', async () => {
    server.use(
      http.get('/api/menus', () =>
        HttpResponse.json({ items: [], total: 0, limit: 10, offset: 0 }),
      ),
    );
    renderApp(['/history']);

    expect(await screen.findByText('Todavía no hay menús guardados')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Crear el primer menú' })).toHaveAttribute('href', '/');
  });

  it('muestra el error de carga', async () => {
    server.use(
      http.get('/api/menus', () =>
        HttpResponse.json(
          { error: { code: 'INTERNAL_ERROR', message: 'Fallo', details: {} } },
          { status: 500 },
        ),
      ),
    );
    renderApp(['/history']);

    expect(await screen.findByText('No se pudo cargar el historial')).toBeInTheDocument();
  });
});
