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
domainReaders.access=async()=>({availability:'available',quality:stale?'STALE':'CURRENT',evaluated_at:'2026-10-04T00:01:00Z',
  items:[{id:'synthetic-access',path:event.new_path!,expected:['synthetic-group-A'],actual:['synthetic-group-B'],owner:'S-1-0-0',group_chain:['synthetic-group-B','synthetic-domain'],drift:'DRIFT',exceptions:[]}]});
domainReaders.hygiene=async()=>({availability:'available',quality:stale?'STALE':'CURRENT',evaluated_at:'2026-10-04T00:01:00Z',
  items:[{id:'synthetic-hygiene',path:event.new_path!,category:'DUPLICATE',value:1024,unit:'BYTES',classification:'CANDIDATE'}]});
domainReaders.diagnostics=async()=>({availability:'available',quality:stale?'STALE':'CURRENT',evaluated_at:'2026-10-04T00:01:00Z',
  items:[{id:'synthetic-pre',phase:'PRE_TRIGGER',occurred_at:'2026-10-04T00:00:00Z',trigger:'SLOW_OPERATION',metric:'LATENCY',value:10},
    {id:'synthetic-trigger',phase:'TRIGGER',occurred_at:'2026-10-04T00:00:01Z',trigger:'SLOW_OPERATION',metric:'LATENCY',value:50},
    {id:'synthetic-post',phase:'POST_TRIGGER',occurred_at:'2026-10-04T00:00:02Z',trigger:'SLOW_OPERATION',metric:'LATENCY',value:25}]});
domainReaders.discovery=async()=>({availability:'available',quality:stale?'STALE':'CURRENT',evaluated_at:'2026-10-04T00:01:00Z',
  items:[{id:'synthetic-series',series_name:'Серия отчётов',schema_family:'synthetic-schema',path:event.new_path!,digitization_candidate:true,workflow_state:'APPROVED',confidence:0.9}]});
domainReaders.policies=async()=>({availability:'available',quality:stale?'STALE':'CURRENT',evaluated_at:'2026-10-04T00:01:00Z',
  items:[{id:'synthetic-policy',name:'synthetic-policy',domain:'RECOVERY',scope:'synthetic-workload',threshold_seconds:3600,threshold_bytes:null,exception_count:0,updated_at:'2026-10-04T00:00:00Z'}]});
domainReaders.audit=async()=>({availability:'available',quality:stale?'STALE':'CURRENT',evaluated_at:'2026-10-04T00:01:00Z',
  items:[{id:'synthetic-audit',occurred_at:'2026-10-04T00:00:00Z',actor:'synthetic-collector',target:'synthetic-batch',action:'INGEST_BATCH_PROCESSED',outcome:'SUCCESS'}]});
void import('../src/main');
