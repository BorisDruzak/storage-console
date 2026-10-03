import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { I18nextProvider } from 'react-i18next';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App';
import { createI18n } from './i18n';
import './style.css';
import { getPreferences } from './preferences';

async function start() {
  const i18n = await createI18n(getPreferences().locale);
  document.title = i18n.t('app.name');
  const client = new QueryClient();
  createRoot(document.getElementById('root')!).render(<StrictMode><I18nextProvider i18n={i18n}><QueryClientProvider client={client}><App /></QueryClientProvider></I18nextProvider></StrictMode>);
}
void start();
