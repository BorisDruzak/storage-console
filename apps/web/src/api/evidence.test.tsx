import { act,render,screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { afterEach,expect,test,vi } from 'vitest';
import { api } from './client';
import { evidenceDeadline } from './evidence';
import { ReadState } from '../components/ReadState';
import { createI18n } from '../i18n';

afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});

test('request elapsed time consumes validity without trusting the wall clock',async()=>{
  const clock=vi.spyOn(performance,'now').mockReturnValue(100);
  vi.stubGlobal('fetch',vi.fn().mockImplementation(async()=>{
    clock.mockReturnValue(700);
    vi.spyOn(Date,'now').mockReturnValue(0);
    return new Response(JSON.stringify({items:[],total:0,limit:50,offset:0}),{headers:{'X-Evidence-Valid-For-Ms':'500'}});
  }));
  const data=await api.sources();
  expect(evidenceDeadline(data)).toBe(600);
  const i18n=await createI18n();
  render(<I18nextProvider i18n={i18n}><ReadState query={{data,isPending:false,isError:false,refetch:async()=>{}}}><p>Исправно</p></ReadState></I18nextProvider>);
  expect(screen.queryByText('Исправно')).not.toBeInTheDocument();
});
test('expired cached data hides healthy children even while refetch remains unresolved',async()=>{
  const i18n=await createI18n();
  const value={capacity:{state:'UNKNOWN',total_bytes:null,used_bytes:null,free_bytes:null,used_percent:null,volume_count:0,current_volume_count:0,unavailable_volume_count:0,latest_inventory_at:null},inventory:{latest_inventory_at:null,volume_count:0,filesystem_types:[],filesystem_objects:0},overall_state:'HEALTHY',freshness:{state:'HEALTHY',source_count:1,current_source_count:1,stale_source_count:0,unknown_source_count:0,last_received_at:null,oldest_event_at:null},evaluated_at:'2026-10-04T00:00:00Z',domains:[],counts:{sources:1,volumes:0,shares:0,filesystem_objects:0}};
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify(value),{headers:{'X-Evidence-Valid-For-Ms':'500'}})));
  const data=await api.overview();
  const query={data,isPending:false,isError:false,refetch:()=>new Promise(()=>{})};
  render(<I18nextProvider i18n={i18n}><ReadState query={query}><p>Исправно</p></ReadState></I18nextProvider>);
  expect(screen.getByText('Исправно')).toBeInTheDocument();
  await act(()=>new Promise(resolve=>setTimeout(resolve,550)));
  expect(screen.queryByText('Исправно')).not.toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Данные устарели');
});
