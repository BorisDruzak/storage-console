import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { afterEach, expect, test, vi } from 'vitest';
import { App } from '../App';
import { createI18n } from '../i18n';
import { ReadResponse } from '../../test-fixtures/http';
import type { Actor } from '../auth/client';

const id = '00000000-0000-4000-8000-000000000001';
const actor: Actor = { id, username: 'synthetic', roles: ['storage_admin'] };
const token = 't'.repeat(43);
const row = { id, source_node_id: id, collector_type: 'WINDOWS', enabled: true,
  version: null, created_at: '2026-01-01T00:00:00Z', last_seen_at: null };
const source = { id, source_type: 'FILESERVER', hostname: 'synthetic-source', fqdn: null,
  instance_id: 'immutable', created_at: row.created_at, freshness: { state: 'UNKNOWN',
    reason: 'NO_COLLECTOR', expected_cadence_seconds: 60, last_success_at: null,
    last_event_at: null, last_collector_at: null, age_seconds: null, cursor: null,
    lag_seconds: null, collector_count: 0, unknown_collector_count: 0, bottleneck_collector_id: null } };
const page = { items: [], total: 0, limit: 50, offset: 0 };
const overview = { overall_state: 'UNKNOWN', domains: [], evaluated_at: row.created_at,
  counts: { sources: 1, volumes: 0, shares: 0, filesystem_objects: 0 },
  freshness: { state: 'UNKNOWN', source_count: 1, current_source_count: 0,
    stale_source_count: 0, unknown_source_count: 1, last_received_at: null, oldest_event_at: null } };

function fixture(current: () => Actor = () => actor) {
  return vi.fn((url: string, options?: RequestInit) => Promise.resolve(
    url === '/api/v1/auth/logout' ? new Response(null, { status: 204 }) :
    url.endsWith('/collectors') && options?.method === 'POST' ? new Response(JSON.stringify({ ...row, token })) :
    new ReadResponse(JSON.stringify(url === '/api/v1/auth/me' ? current() :
      url === '/ready' ? { status: 'ok' } : url.includes('/overview') ? overview :
      url.includes('/collectors?') ? { ...page, items: [row], total: 1 } :
      url === '/api/v1/sources/' + id ? source : page))));
}
async function show() {
  const i18n = await createI18n();
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={cache}><App /></QueryClientProvider></I18nextProvider>);
  return cache;
}
afterEach(() => {
  vi.unstubAllGlobals(); window.location.hash = '';
  document.cookie = '__Host-storage_csrf=; Max-Age=0; path=/; Secure';
});

test.each(['storage_admin', 'storage_operator', 'auditor', 'analyst', 'viewer'] as const)(
  'authenticated %s receives the actual source registration authority', async role => {
    window.location.hash = '#sources';
    vi.stubGlobal('fetch', fixture(() => ({ ...actor, roles: [role] })));
    await show(); await screen.findByText('synthetic');
    await screen.findByText('Данные появятся после подключения источников');
    expect(!!screen.queryByRole('button', { name: 'Зарегистрировать источник' })).toBe(role === 'storage_admin');
  });

test('server permission loss refreshes current roles and removes all source writes', async () => {
  window.location.hash = '#sources'; let current = actor;
  const fallback = fixture(() => current);
  vi.stubGlobal('fetch', vi.fn((url: string, options?: RequestInit) => {
    if (url === '/api/v1/sources' && options?.method === 'POST') {
      current = { ...actor, roles: ['viewer'] };
      return Promise.resolve(new Response('', { status: 403 }));
    }
    return fallback(url, options);
  }));
  document.cookie = '__Host-storage_csrf=' + 'c'.repeat(43) + '; path=/; Secure';
  await show();
  const submit = await screen.findByRole('button', { name: 'Зарегистрировать источник' });
  fireEvent.submit(submit.closest('form')!);
  await waitFor(() => expect(fallback.mock.calls.filter(call => call[0] === '/api/v1/auth/me')).toHaveLength(2));
  await screen.findByText('synthetic');
  expect(screen.queryByRole('button', { name: 'Зарегистрировать источник' })).not.toBeInTheDocument();
});

test('lost source registration response refreshes the list without repeating registration', async () => {
  window.location.hash = '#sources'; let committed = false;
  const fallback = fixture();
  const fetcher = vi.fn((url: string, options?: RequestInit) => {
    if (url === '/api/v1/sources' && options?.method === 'POST') {
      committed = true;
      return Promise.reject(new Error('synthetic response loss'));
    }
    if (url.startsWith('/api/v1/sources?') && committed) {
      return Promise.resolve(new ReadResponse(JSON.stringify({ ...page, items: [source], total: 1 })));
    }
    return fallback(url, options);
  });
  vi.stubGlobal('fetch', fetcher);
  document.cookie = '__Host-storage_csrf=' + 'c'.repeat(43) + '; path=/; Secure';
  await show();
  const submit = await screen.findByRole('button', { name: 'Зарегистрировать источник' });
  fireEvent.submit(submit.closest('form')!);
  await screen.findByRole('alert');
  expect(await screen.findByRole('link', { name: source.hostname })).toBeInTheDocument();
  expect(fetcher.mock.calls.filter(call => call[0] === '/api/v1/sources' && call[1]?.method === 'POST')).toHaveLength(1);
});

test.each(['logout', 'expiry'] as const)('%s unmounts an open key and clears protected query data', async change => {
  window.location.hash = '#sources?id=' + id;
  vi.stubGlobal('fetch', fixture());
  document.cookie = '__Host-storage_csrf=' + 'c'.repeat(43) + '; path=/; Secure';
  const cache = await show();
  fireEvent.click(await screen.findByRole('button', { name: 'Зарегистрировать collector' }));
  expect(await screen.findByLabelText('Ключ collector')).toHaveValue(token);
  if (change === 'logout') fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
  else act(() => window.dispatchEvent(new Event('storage-session-expired')));
  await screen.findByRole('heading', { name: 'Вход в Storage Console' });
  expect(screen.queryByLabelText('Ключ collector')).not.toBeInTheDocument();
  expect(cache.getQueryCache().getAll()).toHaveLength(0);
});
