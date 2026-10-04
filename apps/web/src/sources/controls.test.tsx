import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { afterEach, expect, test, vi } from 'vitest';
import { createI18n } from '../i18n';
import { CollectorControls } from './CollectorControls';
import { SourceRegistrationForm } from './SourceRegistrationForm';
import * as api from './client';

vi.mock('./client', async original => ({ ...await original<typeof api>(),
  listCollectors: vi.fn(), enrollCollector: vi.fn(), rotateCollector: vi.fn(),
  setCollectorEnabled: vi.fn(), registerSource: vi.fn(),
}));
const id = '00000000-0000-4000-8000-000000000001';
const actor = { id, username: 'synthetic', roles: ['storage_admin'] as const };
const row = { id, source_node_id: id, collector_type: 'WINDOWS' as const,
  version: null, enabled: true, created_at: '2026-01-01T00:00:00Z', last_seen_at: null };
const source = { id, source_type: 'FILESERVER' as const };
const token = 't'.repeat(43);
afterEach(() => vi.resetAllMocks());
async function setup(element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const i18n = await createI18n();
  const wrap = (node: React.ReactNode) => <I18nextProvider i18n={i18n}><QueryClientProvider client={client}>{node}</QueryClientProvider></I18nextProvider>;
  const view = render(wrap(element));
  return { ...view, client, replace: (node: React.ReactNode) => view.rerender(wrap(node)) };
}
function collectors() { vi.mocked(api.listCollectors).mockResolvedValue({ items: [row], total: 1, limit: 50, offset: 0 }); }

test('registration sends bounded typed metadata once and handles success', async () => {
  const created = { ...source, hostname: 'synthetic', instance_id: 'immutable', fqdn: null,
    expected_cadence_seconds: 60, created_at: row.created_at };
  vi.mocked(api.registerSource).mockResolvedValue(created);
  const done = vi.fn(); await setup(<SourceRegistrationForm onCreated={done} />);
  fireEvent.change(screen.getByLabelText('Имя узла'), { target: { value: 'synthetic' } });
  fireEvent.change(screen.getByLabelText('Идентификатор экземпляра'), { target: { value: 'immutable' } });
  fireEvent.click(screen.getByRole('button', { name: 'Зарегистрировать источник' }));
  await waitFor(() => expect(done).toHaveBeenCalledWith(created));
  expect(api.registerSource).toHaveBeenCalledWith(expect.objectContaining({ hostname: 'synthetic', instance_id: 'immutable', expected_cadence_seconds: 60 }), expect.any(AbortSignal));
});

test('viewer reads metadata and has no credential or enable controls', async () => {
  collectors(); await setup(<CollectorControls source={source} />);
  expect(await screen.findByText(id)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Зарегистрировать collector' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Обновить ключ' })).not.toBeInTheDocument();
});

test('one-time credential closes and never enters query cache or browser storage', async () => {
  collectors(); vi.mocked(api.enrollCollector).mockResolvedValue({ ...row, token });
  const storage = vi.spyOn(Storage.prototype, 'setItem');
  const { client } = await setup(<CollectorControls source={source} actor={{ ...actor, roles: [...actor.roles] }} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Зарегистрировать collector' }));
  expect(await screen.findByLabelText('Ключ collector')).toHaveValue(token);
  expect(JSON.stringify(client.getQueryCache().getAll().map(query => query.state.data))).not.toContain(token);
  expect(storage).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Закрыть ключ' }));
  expect(screen.queryByLabelText('Ключ collector')).not.toBeInTheDocument();
  storage.mockRestore();
});

test('issued key names its matching collector even when that collector is beyond the current page', async () => {
  const issuedId = '00000000-0000-4000-8000-000000000002';
  vi.mocked(api.listCollectors).mockResolvedValue({ items: [row], total: 51, limit: 50, offset: 0 });
  vi.mocked(api.enrollCollector).mockResolvedValue({ ...row, id: issuedId, token });
  await setup(<CollectorControls source={source} actor={{ ...actor, roles: [...actor.roles] }} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Зарегистрировать collector' }));
  expect(await screen.findByLabelText('Ключ collector')).toHaveValue(token);
  expect(within(screen.getByRole('region', { name: 'Одноразовый показ ключа' })).getByText(issuedId)).toBeInTheDocument();
});

test('pending enrollment rejects double submit and aborts late credential on unmount', async () => {
  collectors(); let resolve!: (value: api.Credential) => void;
  vi.mocked(api.enrollCollector).mockImplementation(() => new Promise(done => { resolve = done; }));
  const { unmount } = await setup(<CollectorControls source={source} actor={{ ...actor, roles: [...actor.roles] }} />);
  const button = await screen.findByRole('button', { name: 'Зарегистрировать collector' });
  fireEvent.click(button); fireEvent.click(button);
  expect(api.enrollCollector).toHaveBeenCalledTimes(1);
  const signal = vi.mocked(api.enrollCollector).mock.calls[0][2]!;
  unmount(); expect(signal.aborted).toBe(true);
  await act(async () => { resolve({ ...row, token }); });
  expect(screen.queryByDisplayValue(token)).not.toBeInTheDocument();
});

test('rotation and disable clear displayed credential and permission failure blocks writes', async () => {
  collectors(); vi.mocked(api.rotateCollector).mockResolvedValue({ ...row, token });
  const refresh = vi.fn(); await setup(<CollectorControls source={source} actor={{ ...actor, roles: [...actor.roles] }} onPermissionDenied={refresh} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Обновить ключ' }));
  expect(await screen.findByLabelText('Ключ collector')).toHaveValue(token);
  vi.mocked(api.setCollectorEnabled).mockRejectedValue(new api.ControlError('AUTH_FORBIDDEN'));
  fireEvent.click(screen.getByRole('button', { name: 'Отключить' }));
  await waitFor(() => expect(refresh).toHaveBeenCalled());
  expect(screen.queryByLabelText('Ключ collector')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Обновить ключ' })).not.toBeInTheDocument();
});

test.each(['source', 'actor', 'role'] as const)('%s change clears a shown key and rejects the previous pending credential', async change => {
  collectors();
  vi.mocked(api.enrollCollector).mockResolvedValueOnce({ ...row, token });
  const admin = { ...actor, roles: [...actor.roles] };
  const view = await setup(<CollectorControls source={source} actor={admin} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Зарегистрировать collector' }));
  expect(await screen.findByLabelText('Ключ collector')).toHaveValue(token);
  let resolve!: (value: api.Credential) => void;
  vi.mocked(api.rotateCollector).mockImplementation(() => new Promise(done => { resolve = done; }));
  fireEvent.click(screen.getByRole('button', { name: 'Обновить ключ' }));
  const signal = vi.mocked(api.rotateCollector).mock.calls[0][1]!;
  const other = '00000000-0000-4000-8000-000000000002';
  view.replace(<CollectorControls source={change === 'source' ? { ...source, id: other } : source}
    actor={change === 'actor' ? { ...admin, id: other } : change === 'role' ? { ...admin, roles: ['viewer'] } : admin} />);
  expect(signal.aborted).toBe(true);
  await act(async () => { resolve({ ...row, token }); });
  expect(screen.queryByLabelText('Ключ collector')).not.toBeInTheDocument();
  expect(JSON.stringify(view.client.getQueryCache().getAll().map(query => query.state.data))).not.toContain(token);
  if (change === 'role') expect(screen.queryByRole('button', { name: 'Обновить ключ' })).not.toBeInTheDocument();
});

test('lost credential response is not retried or echoed and requires a new explicit action', async () => {
  collectors();
  vi.mocked(api.enrollCollector).mockRejectedValue(new Error(token));
  await setup(<CollectorControls source={source} actor={{ ...actor, roles: [...actor.roles] }} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Зарегистрировать collector' }));
  expect(await screen.findByRole('alert')).not.toHaveTextContent(token);
  expect(screen.queryByLabelText('Ключ collector')).not.toBeInTheDocument();
  expect(api.enrollCollector).toHaveBeenCalledTimes(1);
  vi.mocked(api.rotateCollector).mockResolvedValue({ ...row, token });
  fireEvent.click(screen.getByRole('button', { name: 'Обновить ключ' }));
  expect(await screen.findByLabelText('Ключ collector')).toHaveValue(token);
});

test('lost first enrollment response refreshes an initially empty list so explicit rotation can recover', async () => {
  vi.mocked(api.listCollectors).mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
  vi.mocked(api.enrollCollector).mockImplementation(async () => {
    collectors();
    throw new api.ControlError('CONTROL_UNAVAILABLE');
  });
  vi.mocked(api.rotateCollector).mockResolvedValue({ ...row, token });
  await setup(<CollectorControls source={source} actor={{ ...actor, roles: [...actor.roles] }} />);
  await screen.findByText('Данные появятся после подключения источников');
  fireEvent.click(screen.getByRole('button', { name: 'Зарегистрировать collector' }));
  await screen.findByRole('alert');
  fireEvent.click(await screen.findByRole('button', { name: 'Обновить ключ' }));
  expect(await screen.findByLabelText('Ключ collector')).toHaveValue(token);
  expect(api.enrollCollector).toHaveBeenCalledTimes(1);
  expect(api.rotateCollector).toHaveBeenCalledTimes(1);
});

test('disable and explicit re-enable refresh metadata without storing a credential', async () => {
  collectors();
  vi.mocked(api.setCollectorEnabled).mockImplementation(async (_id, enabled) => {
    vi.mocked(api.listCollectors).mockResolvedValue({ items: [{ ...row, enabled }], total: 1, limit: 50, offset: 0 });
    return { ...row, enabled };
  });
  await setup(<CollectorControls source={source} actor={{ ...actor, roles: [...actor.roles] }} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Отключить' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Включить' }));
  await screen.findByRole('button', { name: 'Отключить' });
  expect(vi.mocked(api.setCollectorEnabled).mock.calls.map(call => call[1])).toEqual([false, true]);
  expect(screen.queryByLabelText('Ключ collector')).not.toBeInTheDocument();
});

test('registration ignores a late response on unmount and sends only one pending request', async () => {
  let resolve!: (value: api.SourceRegistration) => void;
  vi.mocked(api.registerSource).mockImplementation(() => new Promise(done => { resolve = done; }));
  const done = vi.fn();
  const view = await setup(<SourceRegistrationForm onCreated={done} />);
  const form = screen.getByRole('button', { name: 'Зарегистрировать источник' }).closest('form')!;
  fireEvent.submit(form); fireEvent.submit(form);
  expect(api.registerSource).toHaveBeenCalledTimes(1);
  const signal = vi.mocked(api.registerSource).mock.calls[0][1]!;
  view.unmount(); expect(signal.aborted).toBe(true);
  await act(async () => { resolve({ ...source, hostname: 'synthetic', instance_id: 'immutable', fqdn: null,
    expected_cadence_seconds: 60, created_at: row.created_at }); });
  expect(done).not.toHaveBeenCalled();
});
