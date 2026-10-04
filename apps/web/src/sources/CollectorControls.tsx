import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { Actor } from '../auth/client';
import { timestamp } from '../components/ReadState';
import { enrollCollector, listCollectors, rotateCollector, setCollectorEnabled,
  type CollectorType, type Credential, type SourceRegistration } from './client';
import { useControlRequest } from './useControlRequest';

type Props = { source: Pick<SourceRegistration, 'id' | 'source_type'>; actor?: Actor; onPermissionDenied?: () => void };
export function CollectorControls(props: Props) {
  const key = `${props.source.id}:${props.actor?.id ?? ''}:${props.actor?.roles.join(',') ?? ''}`;
  return <Panel key={key} {...props} />;
}
function Panel({ source, actor, onPermissionDenied }: Props) {
  const { t, i18n } = useTranslation(); const cache = useQueryClient();
  const [offset, setOffset] = useState(0); const [credential, setCredential] = useState<Credential | null>(null);
  const [blocked, setBlocked] = useState(false);
  const request = useControlRequest(() => { setCredential(null); setBlocked(true); onPermissionDenied?.(); }, refresh);
  const admin = !!actor?.roles.includes('storage_admin') && !blocked;
  const query = useQuery({ queryKey: ['collectors', source.id, offset],
    queryFn: ({ signal }) => listCollectors(source.id, { limit: 50, offset }, signal), retry: false });
  const type: CollectorType = source.source_type === 'FILESERVER' ? 'WINDOWS' : source.source_type;
  function refresh() {
    void cache.invalidateQueries({ queryKey: ['collectors', source.id] });
    void cache.invalidateQueries({ queryKey: ['source', source.id] });
    void cache.invalidateQueries({ queryKey: ['sources'] });
    void cache.invalidateQueries({ queryKey: ['overview'] });
  }
  function issue(operation: (signal: AbortSignal) => Promise<Credential>) {
    if (!admin || request.pending) return;
    setCredential(null);
    void request.run(operation, value => { setCredential(value); refresh(); });
  }
  function enable(id: string, enabled: boolean) {
    if (!admin || request.pending) return;
    setCredential(null); void request.run(signal => setCollectorEnabled(id, enabled, signal), refresh);
  }
  return <section className="source-controls"><h2>{t('sourceControl.collectors')}</h2>
    {request.error ? <p role="alert">{t(`sourceControl.errors.${request.error}`)}</p> : null}
    {admin ? <><p>{t('sourceControl.rotationHelp')}</p><button disabled={request.pending} onClick={() => issue(signal => enrollCollector(source.id, type, signal))}>{t('sourceControl.enroll')}</button></> : null}
    {request.pending ? <p role="status">{t('sourceControl.pending')}</p> : null}
    {credential && admin ? <section className="credential-panel" aria-label={t('sourceControl.oneTime')}>
      <h3>{t('sourceControl.oneTime')}</h3><p>{t('sourceControl.keyHelp')}</p>
      <dl><dt>{t('sourceControl.identity')}</dt><dd><code>{credential.id}</code></dd></dl>
      <label>{t('sourceControl.key')}<input value={credential.token} readOnly autoComplete="off" spellCheck={false} /></label>
      <button onClick={() => setCredential(null)}>{t('sourceControl.close')}</button>
    </section> : null}
    {query.isPending ? <p role="status">{t('common.loading')}</p> : query.isError ? <p role="alert">{t('sourceControl.listFailed')} <button onClick={() => void query.refetch()}>{t('common.retry')}</button></p> : <>
      {query.data.items.length ? <div className="table-scroll"><table><thead><tr>
        <th scope="col">{t('sourceControl.identity')}</th><th scope="col">{t('sourceControl.type')}</th>
        <th scope="col">{t('sourceControl.state')}</th><th scope="col">{t('sources.version')}</th><th scope="col">{t('sourceControl.lastSeen')}</th>
        {admin ? <th scope="col">{t('sourceControl.actions')}</th> : null}
      </tr></thead><tbody>{query.data.items.map(row => <tr key={row.id}>
        <td><code>{row.id}</code></td><td><code>{row.collector_type}</code></td><td>{t(row.enabled ? 'sourceControl.enabled' : 'sourceControl.disabled')}</td>
        <td><code>{row.version ?? t('common.unavailable')}</code></td><td>{timestamp(row.last_seen_at, i18n.language) ?? t('common.unavailable')}</td>
        {admin ? <td><div className="control-actions"><button disabled={request.pending} onClick={() => issue(signal => rotateCollector(row.id, signal))}>{t('sourceControl.rotate')}</button>
          <button disabled={request.pending} onClick={() => enable(row.id, !row.enabled)}>{t(row.enabled ? 'sourceControl.disable' : 'sourceControl.enable')}</button></div></td> : null}
      </tr>)}</tbody></table></div> : <p>{t('common.empty')}</p>}
      <div className="pager"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>{t('common.previous')}</button>
        <span>{t('common.page', { start: offset < query.data.total ? offset + 1 : 0, end: Math.min(offset + 50, query.data.total), total: query.data.total })}</span>
        <button disabled={offset + 50 >= query.data.total || offset + 50 > 1000000} onClick={() => setOffset(offset + 50)}>{t('common.next')}</button></div>
    </>}
  </section>;
}
