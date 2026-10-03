// Browser QA entry only. Vite production build has a single index.html entry;
// this file and its synthetic observations must never enter dist.
import { domainReaders, type ActivityEvent } from '../src/domains/models';
const stale=new URLSearchParams(location.search).get('stale')==='1';
const event: ActivityEvent={id:'synthetic-0',source_id:'synthetic-source',object_id:'synthetic-object',
  occurred_at:'2026-10-04T00:00:01Z',event_type:'WRITE',actor:'Тестовый пользователь',client:'synthetic-client',
  old_path:'\\\\synthetic\\Отчёты\\до.txt',new_path:'\\\\synthetic\\Отчёты\\'+('Длинный путь/'.repeat(20))+'после.txt',confidence:0.8};
domainReaders.activity=async()=>({availability:'available',quality:stale?'STALE':'CURRENT',evaluated_at:'2026-10-04T00:01:00Z',
  items:Array.from({length:100},(_,index)=>({...event,id:'synthetic-'+index}))});
domainReaders.recovery=async()=>({availability:'available',quality:stale?'STALE':'CURRENT',evaluated_at:'2026-10-04T00:01:00Z',
  items:[{id:'synthetic-workload',name:'synthetic-workload',platform_state:'HEALTHY',protection:'UNPROTECTED',steps:{}}]});
void import('../src/main');
