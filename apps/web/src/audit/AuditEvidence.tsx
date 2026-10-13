import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ReadState, timestamp } from '../components/ReadState';
import { RawValue } from '../components/RawValue';
import { link } from '../navigation';
import { auditStream, auditObject, changeAudit, searchAudit, type AuditSearch, type AuditRecord } from './client';

const EVENT_FIELDS = ['account', 'sid', 'domain', 'logon_id', 'client_ip', 'workstation', 'path', 'volume_id', 'handle_id', 'process_id', 'access_mask', 'boot_id', 'generation'] as const;
const DIAGNOSTICS = ['backlog_count', 'backlog_bytes', 'filtered_count', 'bookmark_age_seconds', 'remaining_record_margin', 'gap', 'error_code'] as const;
const FILTER_FIELDS = ['account', 'sid', 'client_ip', 'file_id'] as const;
const DATE_FIELDS = ['start_at', 'end_at'] as const;

function Evidence({ record }: { record: AuditRecord }) {
  const { t, i18n } = useTranslation(); const event = record.evidence;
  return <article className="audit-evidence"><h4>{t('securityAudit.event', { event: event.event_id, record: record.numeric_fields.record_id })}</h4>
    <p>{t(event.event_id === 4663 ? 'securityAudit.accessFact' : event.event_id === 4660 ? 'securityAudit.deleteFact' : 'securityAudit.logonFact')}</p>
    <dl>{EVENT_FIELDS.map(key =>
      <div key={key}><dt>{t(`securityAudit.fields.${key}`)}</dt><dd><RawValue value={record.numeric_fields[key] ?? (event[key] == null ? null : String(event[key]))} /></dd></div>)}
      <dt>{t('securityAudit.fields.time')}</dt><dd>{timestamp(event.occurred_at, i18n.language)}</dd>
      <dt>{t('securityAudit.fields.received')}</dt><dd>{timestamp(record.first_received_at, i18n.language)}</dd>
      <dt>{t('securityAudit.fields.digest')}</dt><dd><code>{record.digest}</code></dd>
      <dt>{t('securityAudit.fields.evidence')}</dt><dd><code>{record.id}</code></dd>
    </dl></article>;
}

export function AuditSourceStatus({ source }: { source: string }) {
  const { t, i18n } = useTranslation();
  const query = useQuery({ queryKey: ['audit-stream', source], queryFn: ({ signal }) => auditStream(source, signal), retry: false, refetchInterval: 10000, gcTime: 0 });
  const data = query.data;
  return <section><h2>{t('securityAudit.stream')}</h2><ReadState query={query}>{data ? <>
    <p role="status">{t(`securityAudit.states.${data.state}`)}</p><p>{t('securityAudit.independent')}</p>
    <dl><dt>{t('securityAudit.fields.time')}</dt><dd>{timestamp(data.evaluated_at, i18n.language)}</dd>
      <dt>{t('securityAudit.fields.collected')}</dt><dd>{timestamp(data.diagnostics?.last_collected_at ?? null, i18n.language) ?? t('common.unavailable')}</dd>
      <dt>{t('securityAudit.fields.accepted')}</dt><dd>{timestamp(data.accepted_at ?? null, i18n.language) ?? t('common.unavailable')}</dd>
      {data.diagnostics ? <>{DIAGNOSTICS.map(key =>
        <div key={key}><dt>{t(`securityAudit.diagnostics.${key}`)}</dt><dd><RawValue value={data.diagnostics?.[key] == null ? null : String(data.diagnostics[key])} /></dd></div>)}</> : null}
    </dl></> : null}</ReadState></section>;
}

export function AuditChangeDetails({ id }: { id: string }) {
  const { t } = useTranslation();
  const query = useQuery({ queryKey: ['audit-change', id], queryFn: ({ signal }) => changeAudit(id, signal), retry: false, refetchInterval: 5000, gcTime: 0 });
  const data = query.data;
  return <ReadState query={query}>{data ? <section className="audit-detail">
    <h3>{t('securityAudit.details')}</h3><p role="status">{t(`securityAudit.classes.${data.classification}`)}</p>
    <p>{t(`securityAudit.reasons.${data.reason}`, { defaultValue: t('securityAudit.reasonUnknown') })}</p>
    <p>{t('securityAudit.interval')} <code>{data.rule_version ?? t('common.unavailable')}</code></p>
    <dl><dt>{t('securityAudit.actor')}</dt><dd>{data.actor?.account ? <RawValue value={data.actor.account} /> : t('securityAudit.unknownActor')}</dd>
      <dt>{t('securityAudit.fields.sid')}</dt><dd><RawValue value={data.actor?.sid ?? null} /></dd>
      <dt>{t('securityAudit.fields.logon_id')}</dt><dd><RawValue value={data.actor ? String(data.actor.logon_id) : null} /></dd>
      <dt>{t('securityAudit.fields.client_ip')}</dt><dd><RawValue value={data.actor?.client_ip ?? null} /></dd>
      <dt>{t('securityAudit.fields.workstation')}</dt><dd><RawValue value={data.actor?.workstation ?? null} /></dd>
      <dt>{t('securityAudit.fields.identityEvidence')}</dt><dd><RawValue value={data.actor?.identity_evidence_id ?? null} /></dd>
    </dl><p>{t('securityAudit.legalBoundary')}</p>
    {data.object_id ? <a href={link('activity', { audit_object_id: data.object_id })}>{t('securityAudit.object')}</a> : null}
    <p>{t(`securityAudit.states.${data.stream.state}`)}</p>
    {data.candidates.map(candidate => <div key={candidate.evidence.id}><p>{t('securityAudit.method')} <code>{candidate.method}</code></p><p>{t(`securityAudit.reasons.${candidate.reason}`, {defaultValue: t('securityAudit.reasonUnknown')})}</p><Evidence record={candidate.evidence} /></div>)}
    {!data.candidates.length ? <p>{t('common.empty')}</p> : null}
  </section> : null}</ReadState>;
}
export function AuditChange({ id, onSelect }: { id: string; onSelect?: (id: string) => void }) {
  const { t } = useTranslation(); const [open, setOpen] = useState(false);
  return <><button aria-expanded={open} onClick={() => onSelect ? onSelect(id) : setOpen(!open)}>{t('securityAudit.displayedEvent')}</button>{open ? <AuditChangeDetails id={id} /> : null}</>;
}

export function AuditBrowser({ source, file }: { source?: string; file?: string }) {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<AuditSearch>({ source_id: source, file_id: file, limit: 50, offset: 0 });
  const [submitted, setSubmitted] = useState<AuditSearch | null>(null);
  const query = useQuery({ queryKey: ['audit-search', submitted], queryFn: ({ signal }) => searchAudit(submitted!, signal), enabled: submitted !== null, retry: false, gcTime: 0 });
  function submit(event: FormEvent) { event.preventDefault(); setSubmitted({ ...filters, offset: 0 }); }
  return <section className="audit-browser"><h2>{t('securityAudit.title')}</h2><p>{t('securityAudit.accessFact')}</p>
    <form onSubmit={submit} className="audit-filters">
      {FILTER_FIELDS.map(key => <label key={key}>{t(`securityAudit.filters.${key}`)}<input maxLength={255} autoComplete="off" value={filters[key] ?? ''} onChange={e => setFilters({ ...filters, [key]: e.target.value || undefined })} /></label>)}
      <label>{t('securityAudit.filters.event')}<select value={filters.event_id ?? ''} onChange={e => setFilters({ ...filters, event_id: e.target.value ? Number(e.target.value) as AuditSearch['event_id'] : undefined })}>
        <option value="">{t('securityAudit.all')}</option>{([4663, 4660, 4624] as const).map(event => <option key={event} value={event}>{t('securityAudit.eventType', { event })}</option>)}</select></label>
      {DATE_FIELDS.map(key => <label key={key}>{t(`securityAudit.filters.${key}`)}<input type="datetime-local" onChange={e => setFilters({ ...filters, [key]: e.target.value ? new Date(e.target.value+'Z').toISOString() : undefined })} /></label>)}
      <button type="submit">{t('securityAudit.search')}</button>
    </form>{submitted ? <ReadState query={query}>{query.data ? <>
      <p>{t('securityAudit.accessFact')}</p>{query.data.items.map(record => <Evidence key={record.id} record={record} />)}
      {!query.data.items.length ? <p>{t('securityAudit.noMatches')}</p> : null}
      <nav aria-label={t('activity.pagination')}><button disabled={!submitted.offset} onClick={() => setSubmitted({ ...submitted, offset: Math.max(0, (submitted.offset ?? 0)-50) })}>{t('common.previous')}</button>
        <button disabled={!query.data.has_more || (submitted.offset ?? 0) >= 10000} onClick={() => setSubmitted({ ...submitted, offset: (submitted.offset ?? 0)+50 })}>{t('common.next')}</button></nav>
    </> : null}</ReadState> : null}
  </section>;
}

export function AuditObjectEvidence({ id }: { id: string }) {
  const { t } = useTranslation();
  const query = useQuery({ queryKey: ['audit-object', id], queryFn: ({ signal }) => auditObject(id, signal), retry: false, gcTime: 0 });
  return <ReadState query={query}>{query.data ? <section><h2>{t('securityAudit.object')}</h2>
    <dl><dt>{t('securityAudit.filters.file_id')}</dt><dd><RawValue value={query.data.file_id} /></dd>
      <dt>{t('securityAudit.fields.volume_id')}</dt><dd><RawValue value={query.data.volume_identity} /></dd></dl>
    <AuditBrowser key={id} source={query.data.source_id} file={query.data.file_id} />
  </section> : null}</ReadState>;
}
