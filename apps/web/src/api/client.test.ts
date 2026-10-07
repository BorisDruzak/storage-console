import { ReadResponse } from '../../test-fixtures/http';
import { afterEach, expect, test, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const overview = {
  capacity:{state:'UNKNOWN',total_bytes:null,used_bytes:null,free_bytes:null,used_percent:null,volume_count:0,current_volume_count:0,unavailable_volume_count:0,latest_inventory_at:null},inventory:{latest_inventory_at:null,volume_count:0,filesystem_types:[],filesystem_objects:0},overall_state: 'UNKNOWN', freshness: {state:'UNKNOWN',source_count:0,current_source_count:0,stale_source_count:0,unknown_source_count:0,last_received_at:null,oldest_event_at:null},
  evaluated_at: '2026-10-04T00:00:00Z', domains: [],
  counts: { sources: 0, volumes: 0, shares: 0, filesystem_objects: 0 },
};

test('valid overview and bounded filtered pages use GET and preserve data', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(new ReadResponse(JSON.stringify(overview)))
    .mockResolvedValueOnce(new ReadResponse(JSON.stringify({ items: [], total: 0, limit: 2, offset: 4 })));
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
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new ReadResponse(JSON.stringify(value))));
  const { api } = await import('./client');
  await expect(api.overview()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});

test('server payload and invalid JSON never become error messages', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(new ReadResponse('private details', { status: 503 }))
    .mockResolvedValueOnce(new ReadResponse('private invalid JSON'));
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
  const fetcher = vi.fn().mockResolvedValue(new ReadResponse(JSON.stringify(overview)));
  vi.stubGlobal('fetch', fetcher);
  const { queries } = await import('./client');
  const client = new QueryClient();
  await Promise.all([client.fetchQuery(queries.overview()), client.fetchQuery(queries.overview())]);
  expect(fetcher).toHaveBeenCalledTimes(1);
  client.clear();
});

test('identical refetch bodies retain the new response evidence deadline', async () => {
  const { queries } = await import('./client');
  const { evidenceDeadline } = await import('./evidence');
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new ReadResponse(JSON.stringify(overview)))));
  const client = new QueryClient();
  const first = await client.fetchQuery(queries.overview());
  await client.invalidateQueries({queryKey:['overview']});
  await client.fetchQuery(queries.overview());
  const second = client.getQueryData(['overview']);
  expect(second).not.toBe(first);
  expect(evidenceDeadline(second)).not.toBeNull();
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
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new ReadResponse(JSON.stringify({ items: [volume], total: 1, limit: 50, offset: 0 }))));
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

test('a late unauthorized response to a cancelled read cannot expire a new session', async () => {
  const controller = new AbortController();
  let finish!: (response: Response) => void;
  const expired = vi.fn();
  window.addEventListener('storage-session-expired', expired);
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finish = resolve; })));
  try {
    const { api } = await import('./client');
    const read = api.overview(controller.signal);
    const rejected = expect(read).rejects.toMatchObject({ code: 'CANCELLED' });
    controller.abort();
    finish(new Response('', { status: 401 }));
    await rejected;
    expect(expired).not.toHaveBeenCalled();
  } finally { window.removeEventListener('storage-session-expired', expired); }
});

test('a cancelled read cannot publish evidence after its response body finishes', async () => {
  const controller = new AbortController();
  const response = new ReadResponse(JSON.stringify(overview));
  vi.spyOn(response, 'text').mockImplementation(async () => {
    controller.abort();
    return JSON.stringify(overview);
  });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
  const { api } = await import('./client');
  await expect(api.overview(controller.signal)).rejects.toMatchObject({ code: 'CANCELLED' });
});


test.each([null,'bad','35001','-1'])('invalid or missing evidence lifetime fails closed: %s',ttl=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify(overview),{headers:ttl===null?{}:{'X-Evidence-Valid-For-Ms':ttl}})));
  return import('./client').then(({api})=>expect(api.overview()).rejects.toMatchObject({code:'INVALID_RESPONSE'}));
});
