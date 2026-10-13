import type { components } from '../api/generated';
import validators from '../api/validators.generated.mjs';
import { recordEvidence } from '../api/evidence';

type Models = components['schemas'];
export type AuditSearch = Models['AuditSearch'];
export type AuditRecord = Models['AuditRecordView'];
export type ChangeAudit = Models['ChangeAudit'];
type Name = 'AuditStream' | 'AuditPage' | 'ChangeAudit' | 'AuditObject';

async function request<N extends Name>(path: string, name: N, signal?: AbortSignal, body?: AuditSearch): Promise<Models[N]> {
  const startedAt = performance.now();
  const timeout = AbortSignal.timeout(10000);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  combined.throwIfAborted();
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body) {
    const values = document.cookie.split(';').map(v => v.trim()).filter(v => v.startsWith('__Host-storage_csrf='));
    const token = values.length === 1 ? values[0].slice('__Host-storage_csrf='.length) : '';
    if (!/^[A-Za-z0-9_-]{43}$/.test(token)) throw new Error('AUTH_REQUIRED');
    headers['X-CSRF-Token'] = token; headers['Content-Type'] = 'application/json';
  }
  const response = await fetch('/api/v1/audit/' + path, { method: body ? 'POST' : 'GET',
    headers, body: body ? JSON.stringify(body) : undefined, credentials: 'same-origin', cache: 'no-store',
    signal: combined });
  combined.throwIfAborted();
  if (response.status === 401) window.dispatchEvent(new Event('storage-session-expired'));
  if (response.status === 403) window.dispatchEvent(new Event('storage-permission-changed'));
  if (!response.ok) throw new Error(response.status === 403 ? 'AUTH_FORBIDDEN' : 'AUDIT_UNAVAILABLE');
  const text = await response.text();
  combined.throwIfAborted();
  if (text.length > 4 * 1024 * 1024) throw new Error('INVALID_RESPONSE');
  const value: unknown = JSON.parse(text);
  if (!validators[name](value)) throw new Error('INVALID_RESPONSE');
  if (name === 'AuditStream' || name === 'ChangeAudit') {
    const ttl = response.headers.get('X-Evidence-Valid-For-Ms');
    if (ttl === null || !/^(0|[1-9][0-9]{0,4})$/.test(ttl) || Number(ttl)>35000) throw new Error('INVALID_RESPONSE');
    recordEvidence(value as object, startedAt, Number(ttl));
  }
  return value as Models[N];
}
function identity(id: string): string {
  if (!/^[0-9a-f-]{36}$/i.test(id)) throw new Error('INVALID_REQUEST');
  return id;
}
export const auditStream = (source: string, signal?: AbortSignal) => request(`sources/${identity(source)}`, 'AuditStream', signal);
export const changeAudit = (change: string, signal?: AbortSignal) => request(`changes/${identity(change)}`, 'ChangeAudit', signal);
export const searchAudit = (filters: AuditSearch, signal?: AbortSignal) => request('search', 'AuditPage', signal, filters);
export const auditObject = (id: string, signal?: AbortSignal) => request(`objects/${identity(id)}`, 'AuditObject', signal);
