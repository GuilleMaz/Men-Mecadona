/** Cliente de la API de catálogo. */

export type SyncStatus = 'running' | 'success' | 'partial' | 'failed';

export type SyncRun = {
  id: number;
  status: SyncStatus;
  started_at: string;
  finished_at: string | null;
  postal_code: string;
  warehouse: string | null;
  categories_ok: number;
  categories_failed: number;
  categories_total: number;
  products_seen: number;
  error: string | null;
  progress: number;
};

export type CatalogStatus = {
  schema_ready: boolean;
  is_syncing: boolean;
  product_count: number;
  category_count: number;
  food_category_count: number;
  last_sync: SyncRun | null;
  last_success_at: string | null;
  prices_captured_at: string | null;
  postal_code: string;
  warehouse: string | null;
};

export type SyncStarted = {
  sync_run_id: number;
  status: 'running';
};

type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
  };
};

/** Error con el código estable que devuelve la API. */
export class CatalogRequestError extends Error {
  readonly code: string | undefined;

  constructor(message: string, code?: string) {
    super(message);
    this.name = 'CatalogRequestError';
    this.code = code;
  }
}

async function readError(response: Response): Promise<CatalogRequestError> {
  try {
    const payload = (await response.json()) as ApiErrorBody;
    const message = payload.error?.message ?? `La API respondió con estado ${response.status}`;
    return new CatalogRequestError(message, payload.error?.code);
  } catch {
    return new CatalogRequestError(`La API respondió con estado ${response.status}`);
  }
}

/** Consulta última sync, progreso y conteos. */
export async function fetchCatalogStatus(): Promise<CatalogStatus> {
  const response = await fetch('/api/catalog/status', {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as CatalogStatus;
}

/** Lanza una sincronización en segundo plano. */
export async function startCatalogSync(): Promise<SyncStarted> {
  const response = await fetch('/api/catalog/sync', {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as SyncStarted;
}
