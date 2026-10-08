import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ReadState, timestamp } from '../components/ReadState';
import { DomainState } from '../components/DomainState';
import { DomainFilter, useDomainFilters } from '../components/DomainFilter';
import { domainReaders, type ActivityEvent, type DomainLoader } from '../domains/models';
import { groupActivity } from '../domains/activity';
import { RawValue } from '../components/RawValue';
import { link, useRoute } from '../navigation';

const activitySection='activity';
const columns=['time','event','actor','client','path','change','confidence','provenance','fileId'] as const;
export function ActivityPage({load=domainReaders.activity}: {load?:DomainLoader<ActivityEvent>}) {
  const {t,i18n}=useTranslation();
  const route=useRoute();
  const offset=route.offset<=10000?route.offset:0;
  const filters={...useDomainFilters(),offset};
  const query=useQuery({queryKey:['activity',filters],queryFn:({signal})=>load(filters,signal),retry:false,
    structuralSharing:false,staleTime:2000,refetchInterval:5000});
  const data=query.data;
  const groups=data?.availability==='available'?groupActivity(data.items):[];
  const page=data?.availability==='available'?data.activity:undefined;
  const pageLink=(value:number)=>link(activitySection,{offset:value,
    ...(filters.source_id?{source_id:filters.source_id}:{}),
    ...(filters.event_type?{event_type:filters.event_type}:{})});
  return <>
    <DomainFilter section={activitySection} events />
    <ReadState query={query}><DomainState data={data}>
      {page ? <p role="status">{t(`activity.continuity.${page.continuity}`)}</p>:null}
      <p>{t('activity.grouping')}</p>
      <div className="table-scroll"><table className="activity-table"><thead><tr>
        {columns.map(column=><th key={column} scope="col">{t(`activity.${column}`)}</th>)}
      </tr></thead><tbody>{groups.map(item=><tr key={item.source_id+item.id}>
        <td>{timestamp(item.first_at,i18n.language)}{item.last_at!==item.first_at?<small>{timestamp(item.last_at,i18n.language)}</small>:null}</td>
        <td>{t(`events.${item.event_type}`)}{item.count>1?<small>{t('activity.groupCount',{count:item.count})}</small>:null}</td>
        <td><RawValue value={item.actor} /></td><td><RawValue value={item.client} /></td>
        <td><RawValue value={item.new_path ?? item.old_path} />{item.path_quality==='UNAVAILABLE'?<small>{t('activity.pathUnknown')}</small>:null}</td>
        <td><dl><dt>{t('activity.before')}</dt><dd><RawValue value={item.old_path} /></dd><dt>{t('activity.after')}</dt><dd><RawValue value={item.new_path} /></dd></dl></td>
        <td>{data?.availability==='available'&&data.quality==='CURRENT'&&item.confidence!==null? t('activity.percent',{value:Math.round(item.confidence*100)}):t('common.unavailable')}</td>
        <td>{item.provenance==='NTFS_USN'?t('activity.usn'):t('common.unavailable')}</td>
        <td><RawValue value={item.file_id ?? null} /></td>
      </tr>)}</tbody></table></div>
      {page ? <nav aria-label={t('activity.pagination')}>
        <a href={pageLink(Math.max(0,offset-page.limit))} aria-disabled={offset===0}
          onClick={e=>{if(offset===0)e.preventDefault();}}>{t('common.previous')}</a>
        <span>{t('common.page',{start:page.total?offset+1:0,end:Math.min(offset+page.limit,page.total),total:page.total})}</span>
        <a href={pageLink(offset+page.limit)} aria-disabled={offset+page.limit>=page.total||offset+page.limit>10000}
          onClick={e=>{if(offset+page.limit>=page.total||offset+page.limit>10000)e.preventDefault();}}>{t('common.next')}</a>
      </nav>:null}
    </DomainState></ReadState>
  </>;
}
