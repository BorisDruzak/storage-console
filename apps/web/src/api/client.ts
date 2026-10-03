import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import { queryOptions } from '@tanstack/react-query';
import type { components } from './generated';
import schemas from './schemas.json';

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

const validator = new Ajv2020({ allErrors: false, strict: true });
addFormats(validator);
const validators = new Map<ResponseName, ReturnType<typeof validator.compile>>();
function decode<N extends ResponseName>(name: N, value: unknown): Models[N] {
  let validate = validators.get(name);
  if (!validate) {
    validate = validator.compile({ ...schemas, $ref: `#/$defs/${name}` });
    validators.set(name, validate);
  }
  if (!validate(value)) throw new ApiError('INVALID_RESPONSE');
  return value as Models[N];
}

async function get<N extends ResponseName>(path: string, name: N, signal?: AbortSignal): Promise<Models[N]> {
  const timeout = AbortSignal.timeout(10000);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  try {
    const response = await fetch(`/api/v1${path}`, {
      method: 'GET', signal: combined, credentials: 'same-origin', headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new ApiError(response.status === 404 ? 'NOT_FOUND' :
      response.status === 401 || response.status === 403 ? 'AUTH_REQUIRED' : 'API_UNAVAILABLE');
    const text = await response.text();
    if (text.length > 2 * 1024 * 1024) throw new ApiError('INVALID_RESPONSE');
    let value: unknown;
    try { value = JSON.parse(text); } catch { throw new ApiError('INVALID_RESPONSE'); }
    return decode(name, value);
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (signal?.aborted) throw new ApiError('CANCELLED');
    if (timeout.aborted) throw new ApiError('TIMEOUT');
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
  overview: () => queryOptions({ queryKey: ['overview'], queryFn: ({ signal }) => api.overview(signal), staleTime: 15000, refetchInterval: 30000 }),
  domains: () => queryOptions({ queryKey: ['domains'], queryFn: ({ signal }) => api.domains(signal), staleTime: 15000 }),
  sources: (options: PageOptions = {}) => {
    const filters = { ...options };
    return queryOptions({ queryKey: ['sources', filters], queryFn: ({ signal }) => api.sources(filters, signal), staleTime: 15000 });
  },
  source: (id: string) => queryOptions({ queryKey: ['source', id], queryFn: ({ signal }) => api.source(id, signal), staleTime: 15000 }),
  volumes: (options: StoragePageOptions = {}) => {
    const filters = { ...options };
    return queryOptions({ queryKey: ['volumes', filters], queryFn: ({ signal }) => api.volumes(filters, signal), staleTime: 15000 });
  },
  shares: (options: StoragePageOptions = {}) => {
    const filters = { ...options };
    return queryOptions({ queryKey: ['shares', filters], queryFn: ({ signal }) => api.shares(filters, signal), staleTime: 15000 });
  },
};
