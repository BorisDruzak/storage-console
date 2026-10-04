import { afterEach, expect, test, vi } from 'vitest';
import * as api from './client';

const id = '00000000-0000-4000-8000-000000000001';
const collector = { id, source_node_id: id, collector_type: 'WINDOWS', version: null,
  enabled: true, created_at: '2026-01-01T00:00:00Z', last_seen_at: null };
const source = { id, source_type: 'FILESERVER', hostname: 'synthetic', fqdn: null,
  instance_id: 'immutable', expected_cadence_seconds: 60, created_at: '2026-01-01T00:00:00Z' };
const csrf = 'c'.repeat(43);

afterEach(() => {
  document.cookie = '__Host-storage_csrf=; Path=/; Secure; Max-Age=0';
  vi.unstubAllGlobals(); vi.restoreAllMocks();
});
function cookie() { document.cookie = `__Host-storage_csrf=${csrf}; Path=/; Secure`; }
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status }); }

test('source and credential writes use secure session CSRF JSON without automatic retries', async () => {
  cookie();
  const fetcher = vi.fn().mockResolvedValueOnce(response(source, 201))
    .mockResolvedValueOnce(response({ ...collector, token: 't'.repeat(43) }, 201))
    .mockResolvedValueOnce(response({ ...collector, token: 'r'.repeat(43) }))
    .mockResolvedValueOnce(response({ ...collector, enabled: false }));
  vi.stubGlobal('fetch', fetcher);
  await expect(api.registerSource({ source_type: 'FILESERVER', hostname: 'synthetic',
    instance_id: 'immutable', expected_cadence_seconds: 60 })).resolves.toEqual(source);
  await expect(api.enrollCollector(id, 'WINDOWS')).resolves.toHaveProperty('token', 't'.repeat(43));
  await expect(api.rotateCollector(id)).resolves.toHaveProperty('token', 'r'.repeat(43));
  await expect(api.setCollectorEnabled(id, false)).resolves.toHaveProperty('enabled', false);
  expect(fetcher.mock.calls.map(call => call[0])).toEqual([
    '/api/v1/sources', `/api/v1/sources/${id}/collectors`,
    `/api/v1/collectors/${id}/rotate-token`, `/api/v1/collectors/${id}`,
  ]);
  for (const [, options] of fetcher.mock.calls) {
    expect(options).toMatchObject({ credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf } });
    expect(options.headers.Authorization).toBeUndefined();
  }
  expect(fetcher.mock.calls[2][1].body).toBe('{}');
  expect(fetcher.mock.calls[3][1].method).toBe('PATCH');
});

test('collector reads return metadata only and bounded pagination', async () => {
  const fetcher = vi.fn().mockResolvedValue(response({ items: [collector], total: 1, limit: 50, offset: 0 }));
  vi.stubGlobal('fetch', fetcher);
  await expect(api.listCollectors(id)).resolves.toHaveProperty('items', [collector]);
  expect(fetcher.mock.calls[0][1]).toMatchObject({ method: 'GET', cache: 'no-store', credentials: 'same-origin' });
  await expect(api.listCollectors(id, { limit: 101 })).rejects.toMatchObject({ code: 'INVALID_REQUEST' });
  await expect(api.listCollectors('../overview')).rejects.toMatchObject({ code: 'INVALID_REQUEST' });
  expect(fetcher).toHaveBeenCalledTimes(1);
});

test('missing CSRF or invalid identity fails before credential transport', async () => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  await expect(api.rotateCollector(id)).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
  cookie();
  await expect(api.rotateCollector('../overview')).rejects.toMatchObject({ code: 'INVALID_REQUEST' });
  expect(fetcher).not.toHaveBeenCalled();
});

test('read or write 401 expires session; permission failure does not expire it', async () => {
  cookie(); const expired = vi.fn();
  window.addEventListener('storage-session-expired', expired);
  try {
    const fetcher = vi.fn().mockResolvedValueOnce(response({}, 401)).mockResolvedValueOnce(response({}, 403));
    vi.stubGlobal('fetch', fetcher);
    await expect(api.rotateCollector(id)).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
    expect(expired).toHaveBeenCalledTimes(1);
    await expect(api.rotateCollector(id)).rejects.toMatchObject({ code: 'AUTH_FORBIDDEN' });
    expect(expired).toHaveBeenCalledTimes(1);
  } finally { window.removeEventListener('storage-session-expired', expired); }
});

test('errors never echo server payload or network secrets and issuance is never retried', async () => {
  cookie();
  const fetcher = vi.fn().mockRejectedValue(new Error('synthetic-secret-must-not-echo'));
  vi.stubGlobal('fetch', fetcher);
  await expect(api.rotateCollector(id)).rejects.toMatchObject({ message: 'CONTROL_UNAVAILABLE' });
  expect(fetcher).toHaveBeenCalledTimes(1);
  for (const [status, code] of [[404, 'NOT_FOUND'], [409, 'CONFLICT'], [422, 'INVALID_REQUEST'], [503, 'CONTROL_UNAVAILABLE']] as const) {
    fetcher.mockResolvedValueOnce(response({ detail: 'synthetic-secret-must-not-echo' }, status));
    await expect(api.rotateCollector(id)).rejects.toMatchObject({ code, message: code });
  }
});

test('malformed, oversized or invalid credential response is discarded', async () => {
  cookie(); const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  for (const value of [{ ...collector, token: 'short' }, { ...collector, token: 't'.repeat(43), token_hash: 'forbidden' }]) {
    fetcher.mockResolvedValueOnce(response(value));
    await expect(api.rotateCollector(id)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  }
  fetcher.mockResolvedValueOnce(new Response('private-invalid-json'));
  await expect(api.rotateCollector(id)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  fetcher.mockResolvedValueOnce(new Response(' '.repeat(262145)));
  await expect(api.rotateCollector(id)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});

test('caller abort discards late success and keeps credentials out of persistent storage', async () => {
  cookie(); const controller = new AbortController();
  const storage = vi.spyOn(Storage.prototype, 'setItem');
  const fetcher = vi.fn().mockImplementation(async () => {
    controller.abort(); return response({ ...collector, token: 't'.repeat(43) });
  });
  vi.stubGlobal('fetch', fetcher);
  await expect(api.rotateCollector(id, controller.signal)).rejects.toMatchObject({ code: 'CANCELLED' });
  expect(storage).not.toHaveBeenCalled();
});

test('cancelled old 401 cannot expire a newer session', async () => {
  cookie(); const controller = new AbortController(); const expired = vi.fn();
  window.addEventListener('storage-session-expired', expired);
  try {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => {
      controller.abort(); return response({}, 401);
    }));
    await expect(api.rotateCollector(id, controller.signal)).rejects.toMatchObject({ code: 'CANCELLED' });
    expect(expired).not.toHaveBeenCalled();
  } finally { window.removeEventListener('storage-session-expired', expired); }
});

test('oversized input fails before POST and aborted read discards metadata', async () => {
  cookie(); const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  await expect(api.registerSource({ source_type: 'FILESERVER', hostname: 'x'.repeat(20000),
    instance_id: 'immutable', expected_cadence_seconds: 60 })).rejects.toMatchObject({ code: 'INVALID_REQUEST' });
  expect(fetcher).not.toHaveBeenCalled();
  const controller = new AbortController(); controller.abort();
  await expect(api.listCollectors(id, {}, controller.signal)).rejects.toMatchObject({ code: 'CANCELLED' });
  expect(fetcher).not.toHaveBeenCalled();
});
