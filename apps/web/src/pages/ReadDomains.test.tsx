import { fireEvent, render, screen, within } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, test } from 'vitest';
import { createI18n } from '../i18n';
import { AccessPage, HygienePage, DiagnosticsPage, DiscoveryPage, PoliciesPage, AuditPage } from './ReadDomains';

async function show(page: React.ReactNode) {
  const i18n=await createI18n();
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{page}</QueryClientProvider></I18nextProvider>);
}
const pages=[AccessPage,HygienePage,DiagnosticsPage,DiscoveryPage,PoliciesPage,AuditPage];
afterEach(()=>{window.location.hash='';});
test.each(pages)('domain shell exposes unavailable evidence without healthy status: %s',async(Page)=>{
  await show(<Page />);
  expect(await screen.findByText('Для этого раздела ещё нет данных источников')).toBeInTheDocument();
  expect(screen.queryByText('Исправно')).not.toBeInTheDocument();
});
test.each(pages)('domain read failure remains a retryable error: %s',async(Page)=>{
  await show(<Page load={async()=>{throw new Error('PRIVATE');}} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить данные');
  expect(screen.queryByText('PRIVATE')).not.toBeInTheDocument();
  expect(screen.queryByText('По выбранным фильтрам записей нет')).not.toBeInTheDocument();
});
test.each(pages)('empty successful domain result stays distinct from unavailable: %s',async(Page)=>{
  await show(<Page load={async()=>({availability:'available',quality:'CURRENT',evaluated_at:'2026-10-04T00:00:00Z',items:[]})} />);
  expect(await screen.findByText('По выбранным фильтрам записей нет')).toBeInTheDocument();
  expect(screen.queryByText('Для этого раздела ещё нет данных источников')).not.toBeInTheDocument();
});
test('hygiene source filter preserves selected category in URL',async()=>{
  window.location.hash='#hygiene?category=LONG_PATH';
  await show(<HygienePage />);
  fireEvent.change(screen.getByLabelText('Идентификатор источника'),{target:{value:'synthetic-source'}});
  fireEvent.click(screen.getByRole('button',{name:'Применить'}));
  expect(new URLSearchParams(window.location.hash.split('?')[1]).get('category')).toBe('LONG_PATH');
});
test('access shows semantic expected/actual, drift, owner, chain and exception independently',async()=>{
  await show(<AccessPage load={async()=>({availability:'available',quality:'CURRENT',evaluated_at:'2026-10-04T00:00:00Z',items:[{
    id:'synthetic-access',path:'\\\\synthetic\\Отчёты',expected:['synthetic-group-A'],actual:['synthetic-group-B'],owner:'S-1-0-0',group_chain:['synthetic-group-B','synthetic-domain'],drift:'DRIFT',exceptions:[{reason:'Тестовое исключение',expires_at:null}],
  }]})}/>);
  expect(await screen.findByText('Расхождение')).toBeInTheDocument();
  expect(screen.getByText('S-1-0-0')).toBeInTheDocument();
  expect(screen.getByText('Тестовое исключение')).toBeInTheDocument();
  expect(screen.queryByText('DRIFT')).not.toBeInTheDocument();
});
test('stale access never reports confirmed semantic match',async()=>{
  await show(<AccessPage load={async()=>({availability:'available',quality:'STALE',evaluated_at:'2026-10-04T00:00:00Z',items:[{id:'synthetic-access',path:'raw',expected:null,actual:null,owner:null,group_chain:null,drift:'MATCH',exceptions:[]}]})}/>);
  expect(await screen.findByText('Устаревшие данные')).toBeInTheDocument();
  expect(screen.queryByText('Соответствует')).not.toBeInTheDocument();
});
test('hygiene translates candidate state and does not imply deletion',async()=>{
  await show(<HygienePage load={async()=>({availability:'available',quality:'CURRENT',evaluated_at:'2026-10-04T00:00:00Z',items:[{id:'synthetic-hygiene',path:'\\\\synthetic\\пустой.txt',category:'DUPLICATE',value:0,unit:'BYTES',classification:'CANDIDATE'}]})}/>);
  expect(await screen.findByText('Кандидат')).toBeInTheDocument();
  expect(screen.getByText('Возраст, размер и похожие имена сами по себе не являются основанием для удаления.')).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Удалить'})).not.toBeInTheDocument();
});
test('diagnostic timeline sorts observations within independent pre/trigger/post sections',async()=>{
  await show(<DiagnosticsPage load={async()=>({availability:'available',quality:'CURRENT',evaluated_at:'2026-10-04T00:00:00Z',items:[
    {id:'synthetic-post',phase:'POST_TRIGGER',occurred_at:'2026-10-04T00:00:03Z',trigger:'SLOW_OPERATION',metric:'LATENCY',value:25},
    {id:'synthetic-pre',phase:'PRE_TRIGGER',occurred_at:'2026-10-04T00:00:01Z',trigger:'SLOW_OPERATION',metric:'LATENCY',value:10},
  ]})}/>);
  const pre=await screen.findByRole('region',{name:'До события'});
  const post=screen.getByRole('region',{name:'После события'});
  expect(within(pre).getByText('10')).toBeInTheDocument();
  expect(within(post).getByText('25')).toBeInTheDocument();
  expect(screen.queryByText('POST_TRIGGER')).not.toBeInTheDocument();
});
test('discovery exposes workflow and schema family while stale confidence stays unavailable',async()=>{
  await show(<DiscoveryPage load={async()=>({availability:'available',quality:'STALE',evaluated_at:'2026-10-04T00:00:00Z',items:[{id:'synthetic-series',series_name:'Серия отчётов',schema_family:'synthetic-schema',path:'raw',digitization_candidate:true,workflow_state:'APPROVED',confidence:0.9}]})}/>);
  expect(await screen.findByText('Серия отчётов')).toBeInTheDocument();
  expect(screen.getByText('synthetic-schema')).toBeInTheDocument();
  expect(screen.queryByText('Одобрено')).not.toBeInTheDocument();
  expect(screen.queryByText('90 %')).not.toBeInTheDocument();
});
