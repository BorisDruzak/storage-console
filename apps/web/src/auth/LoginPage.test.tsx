import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { afterEach, expect, test, vi } from 'vitest';
import { App } from '../App';
import { createI18n } from '../i18n';

async function show() {
  render(<I18nextProvider i18n={await createI18n()}><QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider></I18nextProvider>);
}
afterEach(() => { vi.unstubAllGlobals(); });

test('anonymous user sees labelled Russian login before any read query', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('', { status: 401 }));
  vi.stubGlobal('fetch', fetcher);
  await show();
  expect(await screen.findByRole('heading', { name: 'Вход в Storage Console' })).toBeInTheDocument();
  expect(screen.getByLabelText('Учётная запись')).toBeInTheDocument();
  expect(screen.getByLabelText('Пароль')).toHaveAttribute('type', 'password');
  expect(screen.getByLabelText('Способ входа')).toBeInTheDocument();
  expect(fetcher.mock.calls.every(call => call[0] === '/api/v1/auth/me')).toBe(true);
  expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
});

test('generic failed login clears password without persisting it', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('', { status: 401 }));
  vi.stubGlobal('fetch', fetcher);
  await show();
  await screen.findByRole('heading', { name: 'Вход в Storage Console' });
  fireEvent.change(screen.getByLabelText('Учётная запись'), { target: { value: 'synthetic' } });
  fireEvent.change(screen.getByLabelText('Пароль'), { target: { value: 'synthetic-private-password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Войти' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось войти');
  expect(screen.getByLabelText('Пароль')).toHaveValue('');
  expect(localStorage.getItem('password')).toBeNull();
  expect(sessionStorage.getItem('password')).toBeNull();
});
