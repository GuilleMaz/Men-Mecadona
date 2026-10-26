import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { renderApp } from '@/test/render-app';

describe('App', () => {
  it('muestra la navegación y el formulario de menú', () => {
    renderApp();

    expect(screen.getByRole('link', { name: 'Menú' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('heading', { name: 'Crea tu menú' })).toBeInTheDocument();
  });

  it('navega al catálogo de platos, al historial y a ajustes', async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole('link', { name: 'Historial' }));
    expect(await screen.findByRole('heading', { name: 'Historial de menús' })).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: 'Platos' }));
    expect(screen.getByRole('heading', { name: 'Catálogo de platos' })).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: 'Ajustes' }));
    expect(screen.getByRole('heading', { name: 'Ajustes' })).toBeInTheDocument();
  });

  it('muestra la página no encontrada para rutas desconocidas', () => {
    renderApp(['/ruta-inexistente']);

    expect(screen.getByRole('heading', { name: 'Página no encontrada' })).toBeInTheDocument();
  });

  it('muestra el estado de la API local', async () => {
    renderApp();

    expect(await screen.findByText('API conectada')).toBeInTheDocument();
  });
});
