import type { components } from '../api/generated';
import validators from '../api/validators.generated.mjs';

type Models = components['schemas'];
type ResponseName = 'SourceRegistration' | 'CollectorView' | 'CollectorCredential' | 'Page_CollectorView_';
export type CreateSource = Models['CreateSource'];
export type SourceRegistration = Models['SourceRegistration'];
export type Collector = Models['CollectorView'];
export type Credential = Models['CollectorCredential'];
export type CollectorType = Models['CreateCollector']['collector_type'];
export type ControlErrorCode = 'INVALID_REQUEST' | 'INVALID_RESPONSE' | 'AUTH_REQUIRED' |
  'AUTH_FORBIDDEN' | 'NOT_FOUND' | 'CONFLICT' | 'CONTROL_UNAVAILABLE' | 'CANCELLED' | 'TIMEOUT';
export class ControlError extends Error {
  constructor(readonly code: ControlErrorCode) { super(code); }
}

function identity(value: string): string {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)) {
    throw new ControlError('INVALID_REQUEST');
  }
  return value;
}
function csrf(): string {
  const prefix = '__Host-storage_csrf=';
  const values = document.cookie.split(';').map(part => part.trim()).filter(part => part.startsWith(prefix));
  const value = values.length === 1 ? values[0].slice(prefix.length) : '';
  if (!/^[A-Za-z0-9_-]{43}$/.test(value)) throw new ControlError('AUTH_REQUIRED');
  return value;
}

async function request<N extends ResponseName>(
  method: 'GET' | 'POST' | 'PATCH', path: string, name: N, data?: object, signal?: AbortSignal,
): Promise<Models[N]> {
  const timeout = AbortSignal.timeout(10000);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  const cancelled = () => {
    if (signal?.aborted) throw new ControlError('CANCELLED');
    if (timeout.aborted) throw new ControlError('TIMEOUT');
  };
  const headers: Record<string, string> = { Accept: 'application/json' };
  const body = data === undefined ? undefined : JSON.stringify(data);
  if (body !== undefined && new TextEncoder().encode(body).length > 16384) throw new ControlError('INVALID_REQUEST');
  if (method !== 'GET') { headers['Content-Type'] = 'application/json'; headers['X-CSRF-Token'] = csrf(); }
  try {
    cancelled();
    // Credential issuance is never retried and never enters query/mutation caches.
    const response = await fetch('/api/v1' + path, { method, body, headers, signal: combined,
      credentials: 'same-origin', cache: 'no-store' });
    cancelled();
    if (response.status === 401) {
      window.dispatchEvent(new Event('storage-session-expired'));
      throw new ControlError('AUTH_REQUIRED');
    }
    if (!response.ok) {
      const code: ControlErrorCode = response.status === 403 ? 'AUTH_FORBIDDEN' :
        response.status === 404 ? 'NOT_FOUND' : response.status === 409 ? 'CONFLICT' :
          response.status === 422 ? 'INVALID_REQUEST' : 'CONTROL_UNAVAILABLE';
      throw new ControlError(code);
    }
    const text = await response.text();
    cancelled();
    if (text.length > 262144) throw new ControlError('INVALID_RESPONSE');
    let value: unknown;
    try { value = JSON.parse(text); } catch { throw new ControlError('INVALID_RESPONSE'); }
    if (!validators[name](value)) throw new ControlError('INVALID_RESPONSE');
    return value as Models[N];
  } catch (error) {
    cancelled();
    if (error instanceof ControlError) throw error;
    throw new ControlError('CONTROL_UNAVAILABLE');
  }
}

export async function registerSource(data: CreateSource, signal?: AbortSignal): Promise<SourceRegistration> {
  return request('POST', '/sources', 'SourceRegistration', data, signal);
}
export async function enrollCollector(source: string, type: CollectorType, signal?: AbortSignal): Promise<Credential> {
  return request('POST', `/sources/${identity(source)}/collectors`, 'CollectorCredential', { collector_type: type }, signal);
}
export async function rotateCollector(collector: string, signal?: AbortSignal): Promise<Credential> {
  return request('POST', `/collectors/${identity(collector)}/rotate-token`, 'CollectorCredential', {}, signal);
}
export async function setCollectorEnabled(collector: string, enabled: boolean, signal?: AbortSignal): Promise<Collector> {
  return request('PATCH', `/collectors/${identity(collector)}`, 'CollectorView', { enabled }, signal);
}
export async function listCollectors(
  source: string, options: { limit?: number; offset?: number } = {}, signal?: AbortSignal,
): Promise<Models['Page_CollectorView_']> {
  const { limit = 50, offset = 0 } = options;
  if (!Number.isInteger(limit) || limit < 1 || limit > 100 || !Number.isInteger(offset) || offset < 0 || offset > 1000000) {
    throw new ControlError('INVALID_REQUEST');
  }
  return request('GET', `/sources/${identity(source)}/collectors?limit=${limit}&offset=${offset}`, 'Page_CollectorView_', undefined, signal);
}
