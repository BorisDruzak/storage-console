import { queryOptions } from '@tanstack/react-query';
import type { components } from './generated';
import validators from './validators.generated.mjs';
import { recordEvidence } from './evidence';

type Models = components['schemas'];
type ResponseName = 'Overview' | 'Domains' | 'Source' | 'Freshness' | 'Page_Source_' | 'Page_Volume_' | 'Page_Share_';
export type Overview = Models['Overview'];
export type Source = Models['Source'];
export type Volume = Models['Volume'];
export type Share = Models['Share'];
export type HealthState = Models['Freshness']['state'];
export interface PageOptions { limit?: number; offset?: number }
export interface StoragePageOptions extends PageOptions { source_id?: string }
export type ErrorCode = 'INVALID_REQUEST' | 'INVALID_RESPONSE' | 'API_UNAVAILABLE' | 'NOT_FOUND' | 'AUTH_REQUIRED' | 'CANCELLED' | 'TIMEOUT';

export class ApiError extends Error {
  constructor(public readonly code: ErrorCode) { super(code); }
}

function decode<N extends ResponseName>(name: N, value: unknown): Models[N] {
  if (!validators[name](value)) throw new ApiError('INVALID_RESPONSE');
  return value as Models[N];
}

async function get<N extends ResponseName>(path: string, name: N, signal?: AbortSignal): Promise<Models[N]> {
  const startedAt=performance.now();
  const timeout = AbortSignal.timeout(10000);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  const cancelled = () => {
    if (signal?.aborted) throw new ApiError('CANCELLED');
    if (timeout.aborted) throw new ApiError('TIMEOUT');
  };
  try {
    cancelled();
    const response = await fetch(`/api/v1${path}`, {
      method: 'GET', signal: combined, cache:'no-store', credentials: 'same-origin', headers: { Accept: 'application/json' },
    });
    // A completed response may race cache cancellation or a new login.
    cancelled();
    if (response.status === 401) window.dispatchEvent(new Event('storage-session-expired'));
    if (!response.ok) throw new ApiError(response.status === 404 ? 'NOT_FOUND' :
      response.status === 401 || response.status === 403 ? 'AUTH_REQUIRED' : 'API_UNAVAILABLE');
    const lifetime=response.headers.get('X-Evidence-Valid-For-Ms');
    if (lifetime===null || !/^(0|[1-9][0-9]{0,4})$/.test(lifetime) || Number(lifetime)>35000) throw new ApiError('INVALID_RESPONSE');
    const text = await response.text();
    cancelled();
    if (text.length > 2 * 1024 * 1024) throw new ApiError('INVALID_RESPONSE');
    let value: unknown;
    try { value = JSON.parse(text); } catch { throw new ApiError('INVALID_RESPONSE'); }
    const result=decode(name, value);
    // Monotonic request start includes network, server and JSON decode elapsed
    // time. Server/client wall-clock differences cannot extend evidence lifetime.
    recordEvidence(result,startedAt,Number(lifetime));
    return result;
  } catch (error) {
    cancelled();
    if (error instanceof ApiError) throw error;
    throw new ApiError('API_UNAVAILABLE');
  }
}

function identity(id: string): string {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) throw new ApiError('INVALID_REQUEST');
  return id;
}
function page(options: StoragePageOptions, sourceFilter: boolean): string {
  const { limit = 50, offset = 0, source_id } = options;
  if (!Number.isInteger(limit) || limit < 1 || limit > 100 || !Number.isInteger(offset) || offset < 0 || offset > 1000000) throw new ApiError('INVALID_REQUEST');
  const parameters = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (source_id && sourceFilter) parameters.set('source_id', identity(source_id));
  return `?${parameters}`;
}

export const api = {
  overview: (signal?: AbortSignal) => get('/overview', 'Overview', signal),
  domains: (signal?: AbortSignal) => get('/health/domains', 'Domains', signal),
  sources: async (options: PageOptions = {}, signal?: AbortSignal) => get('/sources' + page(options, false), 'Page_Source_', signal),
  source: async (id: string, signal?: AbortSignal) => get('/sources/' + identity(id), 'Source', signal),
  freshness: async (id: string, signal?: AbortSignal) => get('/sources/' + identity(id) + '/freshness', 'Freshness', signal),
  volumes: async (options: StoragePageOptions = {}, signal?: AbortSignal) => get('/volumes' + page(options, true), 'Page_Volume_', signal),
  shares: async (options: StoragePageOptions = {}, signal?: AbortSignal) => get('/shares' + page(options, true), 'Page_Share_', signal),
};

export const queries = {
  // Every response carries a new monotonic validity deadline, even for identical JSON.
  overview: () => queryOptions({ queryKey: ['overview'], queryFn: ({ signal }) => api.overview(signal), structuralSharing: false, staleTime: 15000, refetchInterval: 30000 }),
  domains: () => queryOptions({ queryKey: ['domains'], queryFn: ({ signal }) => api.domains(signal), structuralSharing: false, staleTime: 15000, refetchInterval: 30000 }),
  sources: (options: PageOptions = {}) => {
    const filters = { ...options };
    return queryOptions({ queryKey: ['sources', filters], queryFn: ({ signal }) => api.sources(filters, signal), structuralSharing: false, staleTime: 15000, refetchInterval: 30000 });
  },
  source: (id: string) => queryOptions({ queryKey: ['source', id], queryFn: ({ signal }) => api.source(id, signal), structuralSharing: false, staleTime: 15000, refetchInterval: 30000 }),
  volumes: (options: StoragePageOptions = {}) => {
    const filters = { ...options };
    return queryOptions({ queryKey: ['volumes', filters], queryFn: ({ signal }) => api.volumes(filters, signal), structuralSharing: false, staleTime: 15000, refetchInterval: 30000 });
  },
  shares: (options: StoragePageOptions = {}) => {
    const filters = { ...options };
    return queryOptions({ queryKey: ['shares', filters], queryFn: ({ signal }) => api.shares(filters, signal), structuralSharing: false, staleTime: 15000, refetchInterval: 30000 });
  },
};
