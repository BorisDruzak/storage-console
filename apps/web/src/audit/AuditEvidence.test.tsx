import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { afterEach, expect, test, vi } from 'vitest';
import { createI18n } from '../i18n';
import { AuditBrowser, AuditChange, AuditSourceStatus } from './AuditEvidence';
import { ActivityPage } from '../pages/ActivityPage';

const id = '00000000-0000-0000-0000-000000000001';
const time = '2026-10-13T00:00:00Z';
const stream = { state: 'NOT_CONFIGURED', evaluated_at: time };
async function show(node: React.ReactNode) {
  render(<I18nextProvider i18n={await createI18n()}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{node}</QueryClientProvider></I18nextProvider>);
}
afterEach(() => { vi.unstubAllGlobals(); window.location.hash=''; document.cookie = '__Host-storage_csrf=; Max-Age=0; path=/'; });

test('uncorrelated change keeps actor explicitly unknown and separates audit coverage', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ change_id: id, object_id: null,
    classification: 'UNKNOWN', reason: 'NO_SCOPED_ACCESS', rule_version: null, actor: null, candidates: [], stream }), {headers:{'X-Evidence-Valid-For-Ms':'35000'}})));
  await show(<AuditChange id={id} />);
  fireEvent.click(screen.getByRole('button'));
  expect(await screen.findByText('Исполнитель не определён')).toBeInTheDocument();
  expect(screen.getByText('Не определён')).toBeInTheDocument();
  expect(screen.getByText('Аудит не настроен')).toBeInTheDocument();
  expect(screen.queryByText('Обоснованная атрибуция')).not.toBeInTheDocument();
});

test('sensitive search fields stay in CSRF protected POST body and never URL', async () => {
  document.cookie = '__Host-storage_csrf='+'a'.repeat(43)+'; path=/; Secure';
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], limit: 50, offset: 0, has_more: false, evaluated_at: time })));
  vi.stubGlobal('fetch', fetcher);
  await show(<AuditBrowser source={id} />);
  fireEvent.change(screen.getByLabelText('Учётная запись'), { target: { value: 'SyntheticUserA' } });
  fireEvent.change(screen.getByLabelText('IP клиента'), { target: { value: '192.0.2.10' } });
  fireEvent.click(screen.getByRole('button', { name: 'Найти свидетельства' }));
  expect(await screen.findByText('По выбранным фильтрам записей нет')).toBeInTheDocument();
  const [url, options] = fetcher.mock.calls[0];
  expect(url).toBe('/api/v1/audit/search');
  expect(options.method).toBe('POST');
  expect(options.headers['X-CSRF-Token']).toBe('a'.repeat(43));
  expect(JSON.parse(options.body)).toMatchObject({ account: 'SyntheticUserA', client_ip: '192.0.2.10', source_id: id });
});

test('Audit GAP is rendered independently and retains safe diagnostics', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ state: 'GAP', evaluated_at: time }), {headers:{'X-Evidence-Valid-For-Ms':'35000'}})));
  await show(<AuditSourceStatus source={id} />);
  expect(await screen.findByText('Аудит: обнаружен разрыв')).toBeInTheDocument();
  expect(screen.getByText('Состояние аудита независимо от непрерывности журнала NTFS USN.')).toBeInTheDocument();
});

test('forbidden direct evidence read never renders previous account', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 403 })));
  await show(<AuditChange id={id} />);
  fireEvent.click(screen.getByRole('button'));
  expect(await screen.findByRole('alert')).toBeInTheDocument();
  expect(screen.queryByText('Учётная запись из Security Event')).not.toBeInTheDocument();
});

test('changing Activity source discards prior private audit filters and submits the new scope', async () => {
  const second = '00000000-0000-0000-0000-000000000002';
  window.location.hash='#activity?source_id='+id;
  document.cookie = '__Host-storage_csrf='+'a'.repeat(43)+'; path=/; Secure';
  const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ items: [], limit: 50, offset: 0, has_more: false, evaluated_at: time })));
  vi.stubGlobal('fetch', fetcher);
  await show(<ActivityPage auditEnabled load={async () => ({availability:'available', quality:'CURRENT', evaluated_at:time, items:[]})} />);
  fireEvent.change(screen.getByLabelText('Учётная запись', {exact:true}), {target:{value:'PrivateScopeA'}});
  fireEvent.click(screen.getByRole('button',{name:'Найти свидетельства'}));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  act(() => { window.location.hash='#activity?source_id='+second; window.dispatchEvent(new HashChangeEvent('hashchange')); });
  expect(screen.getByLabelText('Учётная запись',{exact:true})).toHaveValue('');
  fireEvent.click(screen.getByRole('button',{name:'Найти свидетельства'}));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  expect(JSON.parse(fetcher.mock.calls.at(-1)![1].body)).toMatchObject({source_id:second});
});
