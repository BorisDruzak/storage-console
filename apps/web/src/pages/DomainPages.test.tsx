import { fireEvent, render, screen, within } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, test, vi } from 'vitest';
import { createI18n } from '../i18n';
import { ActivityPage } from './ActivityPage';
import { RecoveryPage } from './RecoveryPage';
import { groupActivity } from '../domains/activity';
import type { ActivityEvent, RecoveryWorkload } from '../domains/models';

async function show(page: React.ReactNode) {
  const i18n = await createI18n();
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{page}</QueryClientProvider></I18nextProvider>);
}
afterEach(() => { window.location.hash = ''; });
const event: ActivityEvent = {id:'event-1',source_id:'synthetic-source',object_id:'synthetic-file',occurred_at:'2026-10-04T00:00:01Z',event_type:'WRITE',actor:'Тестовый пользователь',client:'synthetic-client',old_path:'\\\\synthetic\\Отчёты\\до.txt',new_path:'\\\\synthetic\\Отчёты\\после.txt',confidence:0.8};
const workload: RecoveryWorkload = {id:'synthetic-workload',name:'synthetic-workload',platform_state:'HEALTHY',protection:'UNPROTECTED',steps:{}};

test('domain providers are explicitly unavailable without synthetic production evidence', async () => {
  await show(<RecoveryPage />);
  expect(await screen.findByText('Для этого раздела ещё нет данных источников')).toBeInTheDocument();
  expect(screen.queryByText('Исправно')).not.toBeInTheDocument();
});

test('Activity labels USN provenance, unknown continuity and actor without invented attribution', async () => {
  await show(<ActivityPage load={async()=>({availability:'available',quality:'STALE',
    evaluated_at:'2026-10-08T04:01:00Z',
    activity:{continuity:'GAP',total:1,limit:50,offset:0},
    items:[{...event,actor:null,client:null,confidence:null,provenance:'NTFS_USN',
      path_quality:'UNAVAILABLE',file_id:'synthetic-file-id'}]})}/>);
  expect(await screen.findByText('Непрерывность не подтверждена: обнаружен разрыв журнала')).toBeInTheDocument();
  expect(screen.getByText('Журнал NTFS USN')).toBeInTheDocument();
  expect(screen.getByText('synthetic-file-id')).toBeInTheDocument();
  expect(screen.getByText('Часть пути не определена')).toBeInTheDocument();
  expect(screen.queryByText('Тестовый пользователь')).not.toBeInTheDocument();
  expect(screen.queryByText('80 %')).not.toBeInTheDocument();
});
test('storm groups equivalent events without merging actors, paths or minute boundaries', () => {
  const events = [event, {...event,id:'event-2',occurred_at:'2026-10-04T00:00:02Z'},event,
    {...event,id:'event-3',actor:'other'}, {...event,id:'event-4',new_path:'other'},
    {...event,id:'event-5',occurred_at:'2026-10-04T00:01:01Z'}];
  const groups = groupActivity(events);
  expect(groups).toHaveLength(4);
  expect(groups.find(item=>item.count===2)?.last_at).toBe('2026-10-04T00:00:02Z');
});
test('grouped activity renders translated event, raw paths and bounded confidence', async () => {
  await show(<ActivityPage load={async()=>({availability:'available',quality:'CURRENT',evaluated_at:'2026-10-04T00:01:00Z',items:[event,{...event,id:'event-2'}]})} />);
  expect(await screen.findByText('Событий в группе: 2')).toBeInTheDocument();
  expect(within(screen.getAllByRole('row')[1]).getByText('Запись')).toBeInTheDocument();
  expect(screen.getByText(event.old_path!)).toBeInTheDocument();
  expect(screen.getAllByText(event.new_path!)).toHaveLength(2);
  expect(screen.getByText('80 %')).toBeInTheDocument();
  expect(screen.queryByText('WRITE')).not.toBeInTheDocument();
});
test('source and event URL filters are passed to the adapter', async () => {
  window.location.hash='#activity?source_id=synthetic-source&event_type=WRITE';
  const load=vi.fn().mockResolvedValue({availability:'available',quality:'CURRENT',evaluated_at:'2026-10-04T00:01:00Z',items:[]});
  await show(<ActivityPage load={load}/>);
  expect(await screen.findByText('По выбранным фильтрам записей нет')).toBeInTheDocument();
  expect(load.mock.calls[0][0]).toMatchObject({source_id:'synthetic-source',event_type:'WRITE'});
});
test('healthy platform and unprotected workload remain independent', async () => {
  await show(<RecoveryPage load={async()=>({availability:'available',quality:'CURRENT',evaluated_at:'2026-10-04T00:01:00Z',items:[workload]})}/>);
  const card=await screen.findByRole('article',{name:'synthetic-workload'});
  expect(within(card).getByText('Исправно')).toBeInTheDocument();
  expect(within(card).getByText('Не защищена')).toBeInTheDocument();
  expect(within(card).getAllByText('Нет данных')).toHaveLength(9);
});
test('stale recovery evidence cannot remain healthy or protected', async () => {
  await show(<RecoveryPage load={async()=>({availability:'available',quality:'STALE',evaluated_at:'2026-10-04T00:01:00Z',items:[{...workload,protection:'PROTECTED',steps:{restore:{state:'HEALTHY',observed_at:'2026-10-04T00:00:00Z'}}}]})}/>);
  expect(await screen.findByText('Устаревшие данные')).toBeInTheDocument();
  expect(screen.queryByText('Исправно')).not.toBeInTheDocument();
  expect(screen.queryByText('Защищена')).not.toBeInTheDocument();
});
test('adapter failure supports retry and never shows an empty success', async () => {
  const load=vi.fn().mockRejectedValueOnce(new Error('PRIVATE')).mockResolvedValue({availability:'available',quality:'CURRENT',evaluated_at:'2026-10-04T00:01:00Z',items:[]});
  await show(<ActivityPage load={load}/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить данные');
  expect(screen.queryByText('PRIVATE')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Повторить'}));
  expect(await screen.findByText('По выбранным фильтрам записей нет')).toBeInTheDocument();
});
test('pending adapter renders loading independently of unavailable and empty', async () => {
  await show(<ActivityPage load={()=>new Promise(()=>{})}/>);
  expect(screen.getByRole('status')).toHaveTextContent('Загрузка…');
  expect(screen.queryByText('По выбранным фильтрам записей нет')).not.toBeInTheDocument();
  expect(screen.queryByText('Для этого раздела ещё нет данных источников')).not.toBeInTheDocument();
});
