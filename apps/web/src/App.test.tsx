import { act, fireEvent, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, test, vi } from 'vitest';
import { App } from './App';
import { createI18n } from './i18n';

async function show() {
  const i18n = await createI18n();
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><App /></QueryClientProvider></I18nextProvider>);
}

test('Russian navigation and empty storage never indicate healthy', async () => {
  mockApi();
  await show();
  expect(screen.getByRole('navigation')).toBeInTheDocument();
  expect((await screen.findAllByText('Нет данных')).length).toBeGreaterThan(0);
  expect(screen.queryByText('Исправно')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('link', { name: 'Источники данных' }));
  expect(await screen.findByRole('heading', { name: 'Источники данных' })).toBeInTheDocument();
  expect(await screen.findByText('API доступен')).toBeInTheDocument();
  vi.unstubAllGlobals();
});

test('failed readiness displays error with a retry action', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })));
  await show();
  expect(await screen.findByText('API недоступен')).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: 'Повторить' }).length).toBeGreaterThan(0);
  vi.unstubAllGlobals();
});

const emptyOverview = { evaluated_at: '2026-10-04T00:00:00Z', counts: { sources: 0, volumes: 0, shares: 0, filesystem_objects: 0 }, domains: [] };
const emptyPage = { items: [], total: 0, limit: 50, offset: 0 };
function mockApi() {
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url === '/ready' ? {status:'ok'} : url.includes('/overview') ? emptyOverview : emptyPage)))));
}
afterEach(() => { vi.unstubAllGlobals(); window.location.hash = ''; });

test('storage source filter restores its value when URL changes', async () => {
  const first = '6a83a99d-247d-4e58-8c49-089c703ab42d';
  const second = '6a83a99d-247d-4e58-8c49-089c703ab42e';
  window.location.hash = '#health?tab=volumes&source_id=' + first;
  mockApi();
  await show();
  expect(screen.getByLabelText('Идентификатор источника')).toHaveValue(first);
  await act(async () => { window.location.hash = '#health?tab=volumes&source_id=' + second; window.dispatchEvent(new HashChangeEvent('hashchange')); });
  expect(screen.getByLabelText('Идентификатор источника')).toHaveValue(second);
});

test('rapid apply then back restores URL value even without an intermediate render', async () => {
  const first = '6a83a99d-247d-4e58-8c49-089c703ab42d';
  const second = '6a83a99d-247d-4e58-8c49-089c703ab42e';
  window.location.hash = '#health?tab=volumes&source_id=' + first;
  mockApi();
  await show();
  fireEvent.change(screen.getByLabelText('Идентификатор источника'), {target:{value:second}});
  await act(async () => {
    fireEvent.click(screen.getByRole('button', {name:'Применить'}));
    window.location.hash = '#health?tab=volumes&source_id=' + first;
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
  expect(screen.getByLabelText('Идентификатор источника')).toHaveValue(first);
});

test('source page refreshes evidence while it remains open', async () => {
  vi.useFakeTimers();
  try {
    window.location.hash = '#sources';
    const fetcher = vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url === '/ready' ? {status:'ok'} : url.includes('/overview') ? emptyOverview : emptyPage))));
    vi.stubGlobal('fetch', fetcher);
    await act(async () => { await show(); });
    const before = fetcher.mock.calls.filter(([url]) => url.includes('/sources?')).length;
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(fetcher.mock.calls.filter(([url]) => url.includes('/sources?')).length).toBeGreaterThan(before);
  } finally { vi.useRealTimers(); }
});

test('deep links restore sources and bounded offset from URL', async () => {
  window.location.hash = '#sources?offset=50';
  mockApi();
  await show();
  expect(screen.getByRole('heading', { name: 'Источники данных' })).toBeInTheDocument();
  expect(await screen.findByText('Данные появятся после подключения источников')).toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('/sources?limit=50&offset=50'))).toBe(true);
  await act(async () => { window.location.hash = '#overview'; window.dispatchEvent(new HashChangeEvent('hashchange')); });
  expect(screen.getByRole('heading', { name: 'Обзор' })).toBeInTheDocument();
});

test('overview renders persisted critical domain and unknown coverage', async () => {
  const data = { ...emptyOverview, domains: [{ domain: 'CAPACITY', state: 'CRITICAL', source_count: 2, covered_source_count: 1, unknown_source_count: 1 }] };
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url === '/ready' ? {status:'ok'} : data)))));
  await show();
  expect(await screen.findByText('Критично')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Ёмкость' })).toBeInTheDocument();
  expect(screen.getByText('Нет актуальных данных: 1 из 2')).toBeInTheDocument();
});

test('read errors remain errors while readiness is available', async () => {
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(url === '/ready' ? new Response('{"status":"ok"}') : new Response('private', {status:503}))));
  await show();
  expect(await screen.findByText('API доступен')).toBeInTheDocument();
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить данные');
  expect(screen.queryByText('Исправно')).not.toBeInTheDocument();
});
