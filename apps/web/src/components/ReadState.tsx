import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { HealthState } from '../api/client';
import { getPreferences } from '../preferences';
import { useExpiredEvidence } from '../api/evidence';

export function Status({ state }: { state: HealthState }) {
  const { t } = useTranslation();
  return <span className={'state state-' + state}>{t(`health.${state}`)}</span>;
}
export function ReadState({ query, children }: { query: { data?:unknown; isPending: boolean; isError: boolean; refetch: () => Promise<unknown> }; children: ReactNode }) {
  const { t } = useTranslation();
  const expired=useExpiredEvidence(query.data);
  if (query.isPending) return <p role="status">{t('common.loading')}</p>;
  if (query.isError) return <div role="alert"><p>{t('common.error')}</p><button onClick={() => void query.refetch()}>{t('common.retry')}</button></div>;
  if (expired) return <div><p role="status" className="notice">{t('common.expired')}</p><button onClick={()=>void query.refetch()}>{t('common.refresh')}</button></div>;
  return children;
}
export function Empty() {
  const { t } = useTranslation();
  return <p>{t('common.empty')}</p>;
}
export function timestamp(value: string | null, locale: string) {
  if (!value || !Number.isFinite(Date.parse(value))) return null;
  return new Intl.DateTimeFormat(locale, { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', timeZoneName: 'short', timeZone:getPreferences().timeZone }).format(new Date(value));
}
