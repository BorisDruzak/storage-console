import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { eventTypes, type DomainFilters, type EventType } from '../domains/models';
import { link, useRoute, type Section } from '../navigation';

export function useDomainFilters(): DomainFilters {
  const {params}=useRoute();
  const event=eventTypes.find(item=>item===params.get('event_type'));
  return {source_id:params.get('source_id') || undefined,event_type:event};
}
export function DomainFilter({section,events=false,retainedValues={}}: {section:Section;events?:boolean;retainedValues?:Record<string,string>}) {
  const {t}=useTranslation();
  const filters=useDomainFilters();
  const [source,setSource]=useState(filters.source_id ?? '');
  const [event,setEvent]=useState<EventType | ''>(filters.event_type ?? '');
  useEffect(()=>{
    const restore=()=>{
      const params=new URLSearchParams(window.location.hash.split('?')[1]);
      setSource(params.get('source_id') ?? '');
      setEvent(eventTypes.find(item=>item===params.get('event_type')) ?? '');
    };
    window.addEventListener('hashchange',restore);
    return ()=>window.removeEventListener('hashchange',restore);
  },[]);
  return <form onSubmit={e=>{e.preventDefault();window.location.hash=link(section,{
    ...retainedValues,
    ...(source.trim()?{source_id:source.trim()}:{}),...(events&&event?{event_type:event}:{}),
  });}}>
    <label>{t('common.sourceFilter')}<input value={source} onChange={e=>setSource(e.target.value)} /></label>
    {events ? <label>{t('activity.event')}<select value={event} onChange={e=>setEvent(e.target.value as EventType | '')}>
      <option value="">{t('activity.allEvents')}</option>{eventTypes.map(item=><option key={item} value={item}>{t(`events.${item}`)}</option>)}
    </select></label> : null}
    <button type="submit">{t('common.apply')}</button>
  </form>;
}
