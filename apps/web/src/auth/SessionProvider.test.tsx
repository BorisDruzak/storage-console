import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { afterEach, expect, test, vi } from 'vitest';
import { createI18n } from '../i18n';
import { SessionProvider, useSession } from './SessionProvider';

const actor = { id: '6a83a99d-247d-4e58-8c49-089c703ab42d', username: 'synthetic', roles: ['viewer'] };

function Probe() {
  const session = useSession();
  return <><p>{session.state.kind}</p>{session.state.kind === 'authenticated' ? <p>{session.state.actor.username}</p> : null}<button onClick={() => void session.logout()}>logout</button><button onClick={session.retry}>retry</button></>;
}

async function show(client = new QueryClient()) {
  const i18n = await createI18n();
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><SessionProvider><Probe /></SessionProvider></QueryClientProvider></I18nextProvider>);
  return client;
}

afterEach(() => { vi.unstubAllGlobals(); document.cookie = '__Host-storage_csrf=; Max-Age=0; path=/; Secure'; });

test('restore anonymous session does not expose protected content', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 401 })));
  await show();
  expect(await screen.findByText('anonymous')).toBeInTheDocument();
  expect(screen.queryByText('synthetic')).not.toBeInTheDocument();
});

test('logout clears evidence and sends CSRF while hiding the actor', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(actor))).mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal('fetch', fetcher);
  document.cookie = '__Host-storage_csrf=' + 'a'.repeat(43) + '; path=/; Secure';
  const client = await show();
  expect(await screen.findByText('synthetic')).toBeInTheDocument();
  client.setQueryData(['sensitive'], { evidence: 'synthetic-data' });
  fireEvent.click(screen.getByRole('button', { name: 'logout' }));
  await screen.findByText('anonymous');
  expect(client.getQueryData(['sensitive'])).toBeUndefined();
  expect(fetcher.mock.calls[1][1].headers['X-CSRF-Token']).toBe('a'.repeat(43));
  expect(fetcher.mock.calls[1][1].credentials).toBe('same-origin');
});

test('read 401 event clears old evidence and actor', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(actor))));
  const client = await show();
  await screen.findByText('synthetic');
  client.setQueryData(['sensitive'], actor);
  act(() => window.dispatchEvent(new Event('storage-session-expired')));
  await screen.findByText('anonymous');
  expect(client.getQueryData(['sensitive'])).toBeUndefined();
});

test('late restore response cannot restore an expired actor', async () => {
  let resolve!: (response: Response) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(done => { resolve = done; })));
  await show();
  await waitFor(() => expect(resolve).toBeDefined());
  act(() => window.dispatchEvent(new Event('storage-session-expired')));
  await screen.findByText('anonymous');
  await act(async () => resolve(new Response(JSON.stringify(actor))));
  expect(screen.queryByText('synthetic')).not.toBeInTheDocument();
});

test('logout broadcasts again after revocation so a tab restored during the request expires', async () => {
  const sent: string[] = [];
  vi.stubGlobal('BroadcastChannel', class {
    onmessage = null;
    postMessage(value: string) { sent.push(value); }
    close() { /* synthetic channel */ }
  });
  let finish!: (response: Response) => void;
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(actor)))
    .mockImplementationOnce(() => new Promise<Response>(resolve => { finish = resolve; })));
  document.cookie = '__Host-storage_csrf=' + 'a'.repeat(43) + '; path=/; Secure';
  await show();
  await screen.findByText('synthetic');
  fireEvent.click(screen.getByRole('button', { name: 'logout' }));
  await waitFor(() => expect(finish).toBeDefined());
  expect(sent).toEqual(['expired']);
  await act(async () => finish(new Response(null, { status: 204 })));
  await screen.findByText('anonymous');
  expect(sent).toEqual(['expired', 'expired']);
});

test('failed server logout hides evidence and retries logout rather than restoring the actor', async () => {
  const fetcher = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(actor)))
    .mockResolvedValueOnce(new Response('', { status: 503 }))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal('fetch', fetcher);
  document.cookie = '__Host-storage_csrf=' + 'a'.repeat(43) + '; path=/; Secure';
  const client = await show();
  await screen.findByText('synthetic');
  client.setQueryData(['sensitive'], actor);
  fireEvent.click(screen.getByRole('button', { name: 'logout' }));
  await screen.findByText('error');
  expect(screen.queryByText('synthetic')).not.toBeInTheDocument();
  expect(client.getQueryData(['sensitive'])).toBeUndefined();
  fireEvent.click(screen.getByRole('button', { name: 'retry' }));
  await screen.findByText('anonymous');
  expect(fetcher.mock.calls[2][0]).toBe('/api/v1/auth/logout');
});

test('malformed actor or unavailable server never admits a session', async () => {
  const fetcher = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...actor, roles: ['unexpected-role'] })))
    .mockResolvedValueOnce(new Response('', { status: 503 }))
    .mockResolvedValueOnce(new Response('', { status: 401 }));
  vi.stubGlobal('fetch', fetcher);
  await show();
  await screen.findByText('error');
  expect(screen.queryByText('synthetic')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'retry' }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  await screen.findByText('error');
  fireEvent.click(screen.getByRole('button', { name: 'retry' }));
  await screen.findByText('anonymous');
});

test('a cross-tab expiry clears cache and a changed notification revalidates with the server', async () => {
  let receive!: (event: { data: string }) => void;
  const messages: string[] = [];
  vi.stubGlobal('BroadcastChannel', class {
    set onmessage(handler: (event: { data: string }) => void) { receive = handler; }
    postMessage(value: string) { messages.push(value); }
    close() { /* synthetic channel */ }
  });
  const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(actor)))
    .mockResolvedValueOnce(new Response('', { status: 401 }));
  vi.stubGlobal('fetch', fetcher);
  const client = await show();
  await screen.findByText('synthetic');
  client.setQueryData(['sensitive'], actor);
  act(() => receive({ data: 'expired' }));
  await screen.findByText('anonymous');
  expect(client.getQueryData(['sensitive'])).toBeUndefined();
  expect(messages).toEqual([]);
  act(() => receive({ data: 'changed' }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  await screen.findByText('anonymous');
  expect(screen.queryByText('synthetic')).not.toBeInTheDocument();
});
