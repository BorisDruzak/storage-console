import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ReadState, Status, timestamp } from '../components/ReadState';
import { DomainState } from '../components/DomainState';
import { DomainFilter, useDomainFilters } from '../components/DomainFilter';
import { domainReaders, recoverySteps, type DomainLoader, type RecoveryWorkload } from '../domains/models';

const recoverySection='recovery';
export function RecoveryPage({load=domainReaders.recovery}: {load?:DomainLoader<RecoveryWorkload>}) {
  const {t,i18n}=useTranslation();
  const filters=useDomainFilters();
  const query=useQuery({queryKey:['recovery',filters],queryFn:({signal})=>load(filters,signal),retry:false});
  const data=query.data;
  const items=data?.availability==='available'?data.items:[];
  const current=data?.availability==='available'&&data.quality==='CURRENT';
  return <><DomainFilter section={recoverySection} />
    <ReadState query={query}><DomainState data={data}>
      <p>{t('recovery.boundary')}</p>
      {!items.length ? <ol className="ladder">{recoverySteps.map(step=><li key={step}><h3>{t(`recovery.${step}`)}</h3><Status state={'UNKNOWN'} /></li>)}</ol> : null}
      <div className="workloads">{items.map(item=><article key={item.id} aria-label={item.name}>
        <h2><code>{item.name}</code></h2>
        <dl><dt>{t('recovery.platform')}</dt><dd><Status state={current?item.platform_state:'UNKNOWN'} /></dd>
          <dt>{t('recovery.protection')}</dt><dd>{t(`protection.${current?item.protection:'UNKNOWN'}`)}</dd></dl>
        <ol className="ladder">{recoverySteps.map(step=>{
          const evidence=item.steps[step];
          return <li key={step}><h3>{t(`recovery.${step}`)}</h3>
            <Status state={current?evidence?.state ?? 'UNKNOWN':'UNKNOWN'} />
            <p>{evidence?.observed_at?timestamp(evidence.observed_at,i18n.language):t('common.unavailable')}</p>
            {evidence?.seconds!=null?<p>{t('recovery.seconds',{value:evidence.seconds})}</p>:null}
            {evidence?.consistency?<p>{t(`consistency.${evidence.consistency}`)}</p>:null}
          </li>;
        })}</ol>
      </article>)}</div>
    </DomainState></ReadState>
  </>;
}
