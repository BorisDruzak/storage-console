import { fireEvent, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, test, vi } from 'vitest';
import { App } from './App';
import { createI18n } from './i18n';

async function show() {
  const i18n = await createI18n();
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><App /></QueryClientProvider></I18nextProvider>);
}

test('Russian navigation and empty storage never indicate healthy', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"status":"ok"}')));
  await show();
  expect(screen.getByRole('navigation')).toBeInTheDocument();
  expect(screen.getByText('Нет данных')).toBeInTheDocument();
  expect(screen.queryByText('Исправно')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Источники данных' }));
  expect(screen.getByRole('heading', { name: 'Источники данных' })).toBeInTheDocument();
  expect(await screen.findByText('API доступен')).toBeInTheDocument();
  vi.unstubAllGlobals();
});

test('failed readiness displays error with a retry action', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })));
  await show();
  expect(await screen.findByText('API недоступен')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
  vi.unstubAllGlobals();
});
