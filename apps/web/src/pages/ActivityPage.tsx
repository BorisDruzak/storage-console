import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ReadState, timestamp } from '../components/ReadState';
import { DomainState } from '../components/DomainState';
import { DomainFilter, useDomainFilters } from '../components/DomainFilter';
import { domainReaders, type ActivityEvent, type DomainLoader } from '../domains/models';
import { groupActivity } from '../domains/activity';
import { RawValue } from '../components/RawValue';

const activitySection='activity';
const columns=['time','event','actor','client','path','change','confidence'] as const;
export function ActivityPage({load=domainReaders.activity}: {load?:DomainLoader<ActivityEvent>}) {
  const {t,i18n}=useTranslation();
  const filters=useDomainFilters();
  const query=useQuery({queryKey:['activity',filters],queryFn:({signal})=>load(filters,signal),retry:false});
  const data=query.data;
  const groups=data?.availability==='available'?groupActivity(data.items):[];
  return <>
    <DomainFilter section={activitySection} events />
    <ReadState query={query}><DomainState data={data}>
      <p>{t('activity.grouping')}</p>
      <div className="table-scroll"><table className="activity-table"><thead><tr>
        {columns.map(column=><th key={column} scope="col">{t(`activity.${column}`)}</th>)}
      </tr></thead><tbody>{groups.map(item=><tr key={item.source_id+item.id}>
        <td>{timestamp(item.first_at,i18n.language)}{item.last_at!==item.first_at?<small>{timestamp(item.last_at,i18n.language)}</small>:null}</td>
        <td>{t(`events.${item.event_type}`)}{item.count>1?<small>{t('activity.groupCount',{count:item.count})}</small>:null}</td>
        <td><RawValue value={item.actor} /></td><td><RawValue value={item.client} /></td>
        <td><RawValue value={item.new_path ?? item.old_path} /></td>
        <td><dl><dt>{t('activity.before')}</dt><dd><RawValue value={item.old_path} /></dd><dt>{t('activity.after')}</dt><dd><RawValue value={item.new_path} /></dd></dl></td>
        <td>{data?.availability==='available'&&data.quality==='CURRENT'&&item.confidence!==null? t('activity.percent',{value:Math.round(item.confidence*100)}):t('common.unavailable')}</td>
      </tr>)}</tbody></table></div>
    </DomainState></ReadState>
  </>;
}
