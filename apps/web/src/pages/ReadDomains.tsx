import { useTranslation } from 'react-i18next';
import { DomainPanel } from '../components/DomainPanel';
import { RawValue } from '../components/RawValue';
import { timestamp } from '../components/ReadState';
import { domainReaders, hygieneCategories, diagnosticPhases, type DomainLoader, type AccessRecord,
  type HygieneRecord, type DiagnosticRecord, type DiscoveryRecord, type PolicyRecord, type AuditRecord } from '../domains/models';
import { link, useRoute } from '../navigation';

const accessSection='access',hygieneSection='hygiene',diagnosticsSection='diagnostics',discoverySection='discovery',policiesSection='policies',auditSection='audit';
const accessColumns=['path','expected','actual','drift','owner','chain','exceptions'] as const;
const hygieneColumns=['category','path','value','classification'] as const;
const discoveryColumns=['series','family','path','digitization','workflow','confidence'] as const;
const policyColumns=['name','domain','scope','thresholds','exceptions','updated'] as const;
const auditColumns=['time','actor','action','target','outcome'] as const;

export function AccessPage({load=domainReaders.access}:{load?:DomainLoader<AccessRecord>}) {
  const {t,i18n}=useTranslation();
  const list=(items:string[] | null)=>items===null?t('common.unavailable'):items.length?items.join('\n'):t('access.none');
  return <DomainPanel section={accessSection} load={load}>{(items,current)=><div className="table-scroll"><table className="domain-table"><thead><tr>
    {accessColumns.map(key=><th key={key} scope="col">{t(`access.${key}`)}</th>)}
  </tr></thead><tbody>{items.map(item=><tr key={item.id}>
    <td><RawValue value={item.path} /></td><td><RawValue value={list(item.expected)} /></td><td><RawValue value={list(item.actual)} /></td>
    <td>{t(`drift.${current?item.drift:'UNKNOWN'}`)}</td><td><RawValue value={item.owner} /></td><td><RawValue value={list(item.group_chain)} /></td>
    <td>{item.exceptions.length?<ul>{item.exceptions.map((exception,index)=><li key={index}><RawValue value={exception.reason} /><small>{exception.expires_at?timestamp(exception.expires_at,i18n.language):t('access.noExpiry')}</small></li>)}</ul>:t('access.noExceptions')}</td>
  </tr>)}</tbody></table></div>}</DomainPanel>;
}
export function HygienePage({load=domainReaders.hygiene}:{load?:DomainLoader<HygieneRecord>}) {
  const {t,i18n}=useTranslation();
  const {params}=useRoute();
  const category=hygieneCategories.find(item=>item===params.get('category'));
  const source=params.get('source_id');
  const values:Record<string,string>=source?{source_id:source}:{};
  return <><nav className="tabs" aria-label={t('navigation.hygiene')}>
    <a href={link(hygieneSection,values)} aria-current={!category?'page':undefined}>{t('hygiene.all')}</a>
    {hygieneCategories.map(item=><a key={item} href={link(hygieneSection,{...values,category:item})} aria-current={category===item?'page':undefined}>{t(`hygieneCategories.${item}`)}</a>)}
  </nav><DomainPanel section={hygieneSection} load={load} filters={{category}}>{(items,current)=><>
    <p>{t('hygiene.boundary')}</p>
    <div className="table-scroll"><table><thead><tr>{hygieneColumns.map(key=><th key={key} scope="col">{t(`hygiene.${key}`)}</th>)}</tr></thead><tbody>
      {items.map(item=><tr key={item.id}><td>{t(`hygieneCategories.${item.category}`)}</td><td><RawValue value={item.path} /></td>
        <td>{item.value===null?t('common.unavailable'):t(`units.${item.unit}`,{value:item.value.toLocaleString(i18n.language)})}</td>
        <td>{t(`classification.${current?item.classification:'UNKNOWN'}`)}</td></tr>)}
    </tbody></table></div>
  </>}</DomainPanel></>;
}
export function DiagnosticsPage({load=domainReaders.diagnostics}:{load?:DomainLoader<DiagnosticRecord>}) {
  const {t,i18n}=useTranslation();
  return <DomainPanel section={diagnosticsSection} load={load}>{items=><div className="timeline">
    {diagnosticPhases.map(phase=><section key={phase} aria-label={t(`diagnosticPhases.${phase}`)}>
      <h2>{t(`diagnosticPhases.${phase}`)}</h2>
      <ol>{items.filter(item=>item.phase===phase).sort((a,b)=>Date.parse(a.occurred_at)-Date.parse(b.occurred_at)).map(item=><li key={item.id}>
        <p>{timestamp(item.occurred_at,i18n.language)}</p><p>{t(`diagnosticTriggers.${item.trigger}`)}</p>
        <dl><dt>{t(`diagnosticMetrics.${item.metric}`)}</dt><dd>{item.value?.toLocaleString(i18n.language) ?? t('common.unavailable')}</dd></dl>
      </li>)}</ol>
      {!items.some(item=>item.phase===phase)?<p>{t('common.unavailable')}</p>:null}
    </section>)}
  </div>}</DomainPanel>;
}
export function DiscoveryPage({load=domainReaders.discovery}:{load?:DomainLoader<DiscoveryRecord>}) {
  const {t}=useTranslation();
  return <DomainPanel section={discoverySection} load={load}>{(items,current)=><>
    <p>{t('discovery.boundary')}</p><div className="table-scroll"><table className="domain-table"><thead><tr>
      {discoveryColumns.map(key=><th key={key} scope="col">{t(`discovery.${key}`)}</th>)}
    </tr></thead><tbody>{items.map(item=><tr key={item.id}>
      <td><RawValue value={item.series_name} /></td><td><RawValue value={item.schema_family} /></td><td><RawValue value={item.path} /></td>
      <td>{!current||item.digitization_candidate===null?t('common.unavailable'):t(item.digitization_candidate?'discovery.candidate':'discovery.notCandidate')}</td>
      <td>{t(`workflow.${current?item.workflow_state:'UNKNOWN'}`)}</td>
      <td>{current&&item.confidence!==null?t('activity.percent',{value:Math.round(item.confidence*100)}):t('common.unavailable')}</td>
    </tr>)}</tbody></table></div>
  </>}</DomainPanel>;
}
export function PoliciesPage({load=domainReaders.policies}:{load?:DomainLoader<PolicyRecord>}) {
  const {t,i18n}=useTranslation();
  return <DomainPanel section={policiesSection} load={load}>{items=><div className="table-scroll"><table className="domain-table"><thead><tr>
    {policyColumns.map(key=><th key={key} scope="col">{t(`policies.${key}`)}</th>)}
  </tr></thead><tbody>{items.map(item=><tr key={item.id}>
    <td><RawValue value={item.name} /></td><td>{t(`domains.${item.domain}`)}</td><td><RawValue value={item.scope} /></td>
    <td><dl><dt>{t('policies.seconds')}</dt><dd>{item.threshold_seconds?.toLocaleString(i18n.language) ?? t('common.unavailable')}</dd>
      <dt>{t('policies.bytes')}</dt><dd>{item.threshold_bytes?.toLocaleString(i18n.language) ?? t('common.unavailable')}</dd></dl></td>
    <td>{item.exception_count}</td><td>{timestamp(item.updated_at,i18n.language) ?? t('common.unavailable')}</td>
  </tr>)}</tbody></table></div>}</DomainPanel>;
}
export function AuditPage({load=domainReaders.audit}:{load?:DomainLoader<AuditRecord>}) {
  const {t,i18n}=useTranslation();
  return <DomainPanel section={auditSection} load={load}>{items=><div className="table-scroll"><table><thead><tr>
    {auditColumns.map(key=><th key={key} scope="col">{t(`audit.${key}`)}</th>)}
  </tr></thead><tbody>{items.map(item=><tr key={item.id}>
    <td>{timestamp(item.occurred_at,i18n.language)}</td><td><RawValue value={item.actor} /></td><td>{t(`auditActions.${item.action}`)}</td>
    <td><RawValue value={item.target} /></td><td>{t(`auditOutcomes.${item.outcome}`)}</td>
  </tr>)}</tbody></table></div>}</DomainPanel>;
}
