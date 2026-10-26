import { useQuery } from '@tanstack/react-query';
import { CircleAlert, CircleCheck, LoaderCircle } from 'lucide-react';

type HealthResponse = { status: 'ok' };

function isHealthResponse(value: unknown): value is HealthResponse {
  return typeof value === 'object' && value !== null && 'status' in value && value.status === 'ok';
}

async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/health', {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`La API respondio con estado ${response.status}`);
  }
  const payload: unknown = await response.json();
  if (!isHealthResponse(payload)) {
    throw new Error('Respuesta de salud invalida');
  }
  return payload;
}

/** Indicador compacto del estado de la API local. */
export function BackendStatus() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    staleTime: 30_000,
    retry: 0,
  });

  if (health.isPending) {
    return (
      <span
        role="status"
        aria-label="Estado de la API"
        className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground"
      >
        <LoaderCircle aria-hidden="true" className="size-3.5 animate-spin" />
        Comprobando API...
      </span>
    );
  }

  if (health.isError) {
    return (
      <span
        role="status"
        aria-label="Estado de la API"
        className="inline-flex items-center gap-1.5 rounded-full border border-destructive/30 bg-destructive/5 px-2.5 py-1 text-xs font-medium text-destructive"
      >
        <CircleAlert aria-hidden="true" className="size-3.5" />
        API no disponible
      </span>
    );
  }

  return (
    <span
      role="status"
      aria-label="Estado de la API"
      className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/5 px-2.5 py-1 text-xs font-medium text-primary"
    >
      <CircleCheck aria-hidden="true" className="size-3.5" />
      API conectada
    </span>
  );
}
