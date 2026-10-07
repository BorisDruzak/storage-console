import { render, screen, within } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, test, vi } from 'vitest';
import { ReadResponse } from '../../test-fixtures/http';
import { createI18n } from '../i18n';
import { OverviewPage } from './OverviewPage';
import { getPreferences, preferencesKey } from '../preferences';
import { timestamp } from '../components/ReadState';

const capacity = { state:'OBSERVE',total_bytes:1099511627776,used_bytes:824633720832,free_bytes:274877906944,used_percent:75,volume_count:2,current_volume_count:1,unavailable_volume_count:1,latest_inventory_at:'2026-10-07T10:00:00Z' };
const overview = { counts:{sources:1,volumes:2,shares:0,filesystem_objects:42},domains:[],overall_state:'UNKNOWN',evaluated_at:'2026-10-07T10:00:00Z',freshness:{state:'HEALTHY',source_count:1,current_source_count:1,stale_source_count:0,unknown_source_count:0,last_received_at:'2026-10-07T10:00:00Z',oldest_event_at:'2026-10-07T10:00:00Z'},capacity,inventory:{volume_count:2,filesystem_types:['NTFS'],filesystem_objects:42,latest_inventory_at:'2026-10-07T10:00:00Z'} };
afterEach(()=>{vi.unstubAllGlobals();localStorage.clear();window.dispatchEvent(new StorageEvent('storage',{key:null}));});
async function show(data:unknown) {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new ReadResponse(JSON.stringify(data))));
  const i18n=await createI18n();
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><OverviewPage /></QueryClientProvider></I18nextProvider>);
  await screen.findByText('Объекты файловой системы: 42');
}
test('measured capacity uses IEC values and leaves filesystem and overall health unknown',async()=>{
  await show(overview);
  const card=screen.getByRole('heading',{name:'Ёмкость'}).closest('article')!;
  expect(within(card).getByText('Наблюдение')).toBeInTheDocument();
  expect(card).toHaveTextContent('Использовано: 768 ГиБ');
  expect(card).toHaveTextContent('Свободно: 256 ГиБ');
  expect(card).toHaveTextContent('Всего: 1 ТиБ');
  expect(card).toHaveTextContent('75');
  expect(card).toHaveTextContent('Томов с актуальными данными: 1 из 2');
  expect(card).toHaveTextContent('Томов без актуальной ёмкости: 1');
  const filesystem=screen.getByRole('heading',{name:'Файловая система NTFS'}).closest('article')!;
  expect(filesystem).toHaveTextContent('Нет данных');
  expect(filesystem).toHaveTextContent('Обнаружено томов: 2');
  expect(filesystem).toHaveTextContent('Данные о целостности файловой системы ещё не собираются');
  expect(filesystem).toHaveTextContent('15:00:00');
  expect(screen.queryByText('OBSERVE')).not.toBeInTheDocument();
  expect(screen.queryByText('UNKNOWN')).not.toBeInTheDocument();
  expect(screen.getByRole('heading',{name:'Общее состояние'}).closest('article')).toHaveTextContent('Нет данных');
});
test('unknown capacity exposes missing coverage without a green state',async()=>{
  await show({...overview,capacity:{...capacity,state:'UNKNOWN',current_volume_count:0,unavailable_volume_count:2,total_bytes:null,used_bytes:null,free_bytes:null,used_percent:null,latest_inventory_at:null}});
  const card=screen.getByRole('heading',{name:'Ёмкость'}).closest('article')!;
  expect(card).toHaveTextContent('Нет данных');
  expect(card).toHaveTextContent('Томов без актуальной ёмкости: 2');
  expect(within(card).queryByText('Исправно')).not.toBeInTheDocument();
});
test('clean browser defaults to business time and preserves explicit UTC',()=>{
  expect(getPreferences()).toEqual({locale:'ru-RU',timeZone:'Asia/Yekaterinburg'});
  expect(timestamp('2026-10-07T10:00:00Z','ru-RU')).toContain('15:00:00');
  localStorage.setItem(preferencesKey,JSON.stringify({locale:'ru-RU',timeZone:'UTC'}));
  expect(getPreferences().timeZone).toBe('UTC');
  expect(timestamp('2026-10-07T10:00:00Z','ru-RU')).toContain('10:00:00');
});
