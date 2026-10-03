import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, test, vi } from 'vitest';
import { createI18n } from './i18n';
import { App } from './App';
import { getPreferences, savePreferences, preferencesKey } from './preferences';
import { timestamp } from './components/ReadState';
afterEach(()=>{vi.restoreAllMocks();savePreferences({locale:'ru-RU',timeZone:'UTC'});localStorage.clear();window.dispatchEvent(new StorageEvent('storage',{key:null}));window.location.hash='';vi.unstubAllGlobals();});
test.each(['{bad','null','[]','{"locale":"invalid","timeZone":"invalid"}'])('invalid stored preferences safely recover: %s',value=>{
  localStorage.setItem(preferencesKey,value);
  expect(getPreferences()).toEqual({locale:'ru-RU',timeZone:'UTC'});
});
test('timestamp follows configured timezone and DST and rejects invalid dates',()=>{
  savePreferences({locale:'ru-RU',timeZone:'Europe/Berlin'});
  expect(timestamp('2026-03-29T00:30:00Z','ru-RU')).toContain('01:30');
  expect(timestamp('2026-03-29T01:30:00Z','ru-RU')).toContain('03:30');
  expect(timestamp('invalid','ru-RU')).toBeNull();
});
test('denied storage keeps valid preferences temporarily without claiming persistence',()=>{
  vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('PRIVATE');});
  expect(savePreferences({locale:'en-US',timeZone:'UTC'})).toBe(false);
  expect(getPreferences().locale).toBe('en-US');
});
test('settings validate timezone and update language, timestamps and document language',async()=>{
  const i18n=await createI18n();window.location.hash='#settings';
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('',{status:503})));
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><App /></QueryClientProvider></I18nextProvider>);
  fireEvent.change(screen.getByLabelText('Часовой пояс'),{target:{value:'not-a-zone'}});
  fireEvent.click(screen.getByRole('button',{name:'Сохранить настройки'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Укажите корректный часовой пояс');
  fireEvent.change(screen.getByLabelText('Часовой пояс'),{target:{value:'Asia/Yekaterinburg'}});
  fireEvent.change(screen.getByLabelText('Язык'),{target:{value:'en-US'}});
  fireEvent.click(screen.getByRole('button',{name:'Сохранить настройки'}));
  expect(await screen.findByRole('heading',{name:'Settings'})).toBeInTheDocument();
  await waitFor(()=>expect(document.documentElement.lang).toBe('en-US'));
  expect(JSON.parse(localStorage.getItem(preferencesKey)!)).toEqual({locale:'en-US',timeZone:'Asia/Yekaterinburg'});
});
