import { afterEach, expect, test, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const overview = {
  evaluated_at: '2026-10-04T00:00:00Z', domains: [],
  counts: { sources: 0, volumes: 0, shares: 0, filesystem_objects: 0 },
};

test('valid overview and bounded filtered pages use GET and preserve data', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(overview)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0, limit: 2, offset: 4 })));
  vi.stubGlobal('fetch', fetcher);
  const { api } = await import('./client');
  expect(await api.overview()).toEqual(overview);
  const source = '6a83a99d-247d-4e58-8c49-089c703ab42d';
  expect((await api.volumes({ limit: 2, offset: 4, source_id: source })).items).toEqual([]);
  expect(fetcher.mock.calls[1][0]).toBe(`/api/v1/volumes?limit=2&offset=4&source_id=${source}`);
  expect(fetcher.mock.calls[0][1].method).toBe('GET');
});

test.each([
  { ...overview, counts: { sources: -1 } },
  { ...overview, evaluated_at: 'not-a-date' },
  { ...overview, domains: [{ domain: 'CAPACITY', state: 'GREEN', source_count: 0, covered_source_count: 0, unknown_source_count: 0 }] },
])('malformed successful responses fail safely', async value => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(value))));
  const { api } = await import('./client');
  await expect(api.overview()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});

test('server payload and invalid JSON never become error messages', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(new Response('private details', { status: 503 }))
    .mockResolvedValueOnce(new Response('private invalid JSON'));
  vi.stubGlobal('fetch', fetcher);
  const { api } = await import('./client');
  await expect(api.overview()).rejects.toMatchObject({ message: 'API_UNAVAILABLE', code: 'API_UNAVAILABLE' });
  await expect(api.overview()).rejects.toMatchObject({ message: 'INVALID_RESPONSE' });
});

test('query cancellation passes an abort signal and returns a safe code', async () => {
  const controller = new AbortController();
  vi.stubGlobal('fetch', vi.fn((_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('private', 'AbortError')));
    controller.abort();
  })));
  const { api } = await import('./client');
  await expect(api.overview(controller.signal)).rejects.toMatchObject({ code: 'CANCELLED' });
});

test('identical query keys deduplicate concurrent fetches', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(overview)));
  vi.stubGlobal('fetch', fetcher);
  const { queries } = await import('./client');
  const client = new QueryClient();
  await Promise.all([client.fetchQuery(queries.overview()), client.fetchQuery(queries.overview())]);
  expect(fetcher).toHaveBeenCalledTimes(1);
  client.clear();
});

test('invalid pagination is rejected before transport', async () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  const { api } = await import('./client');
  await expect(api.sources({ limit: 101 })).rejects.toMatchObject({ code: 'INVALID_REQUEST' });
  expect(fetcher).not.toHaveBeenCalled();
});

test('source identifiers cannot inject query or path components', async () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  const { api } = await import('./client');
  await expect(api.source('../overview')).rejects.toMatchObject({ code: 'INVALID_REQUEST' });
  await expect(api.shares({ source_id: 'source&limit=999' })).rejects.toMatchObject({ code: 'INVALID_REQUEST' });
  expect(fetcher).not.toHaveBeenCalled();
});

test('Cyrillic paths and UNC aliases are preserved by schema validation', async () => {
  const volume = {
    id: '6a83a99d-247d-4e58-8c49-089c703ab42d', source_node_id: '6a83a99d-247d-4e58-8c49-089c703ab42e',
    unique_identity: 'synthetic-volume', filesystem: 'NTFS', label: 'Отчёты',
    total_bytes: null, free_bytes: null, first_seen_at: '2026-10-04T00:00:00Z', last_seen_at: '2026-10-04T00:00:00Z',
    mount_aliases: ['\\\\synthetic\\Общие отчёты'], quality: 'PARTIAL',
  };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [volume], total: 1, limit: 50, offset: 0 }))));
  const { api } = await import('./client');
  expect((await api.volumes()).items[0]).toEqual(volume);
});

test('timeout has its own safe code', async () => {
  const timeout = new AbortController();
  vi.spyOn(AbortSignal, 'timeout').mockReturnValue(timeout.signal);
  vi.stubGlobal('fetch', vi.fn((_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('private', 'AbortError')));
    timeout.abort();
  })));
  const { api } = await import('./client');
  await expect(api.overview()).rejects.toMatchObject({ code: 'TIMEOUT' });
});
