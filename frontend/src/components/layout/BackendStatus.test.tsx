import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { server } from '@/test/server';
import { renderApp } from '@/test/render-app';

describe('BackendStatus', () => {
  it('confirma la conexión cuando /api/health responde ok', async () => {
    renderApp();

    expect(await screen.findByText('API conectada')).toBeInTheDocument();
  });

  it('avisa cuando la API no responde', async () => {
    server.use(
      http.get('/api/health', () => HttpResponse.json({ detail: 'sin servicio' }, { status: 503 })),
    );

    renderApp();

    expect(await screen.findByText('API no disponible')).toBeInTheDocument();
  });

  it('avisa cuando la respuesta de salud no es válida', async () => {
    server.use(http.get('/api/health', () => HttpResponse.json({ status: 'degraded' })));

    renderApp();

    expect(await screen.findByText('API no disponible')).toBeInTheDocument();
  });
});
