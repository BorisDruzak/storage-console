import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { DomainRead } from '../domains/models';
import { timestamp } from './ReadState';

export function DomainState<T>({data,children}: {data: DomainRead<T> | undefined; children:ReactNode}) {
  const {t,i18n}=useTranslation();
  if (!data) return null;
  if (data.availability==='unavailable') return <><p role="status">{t('common.unavailableEvidence')}</p>{children}</>;
  return <>
    <p>{t('overview.evaluated',{at:timestamp(data.evaluated_at,i18n.language)})}</p>
    {data.quality==='STALE' ? <p role="status" className="notice">{t('health.STALE')}</p> : null}
    {!data.items.length ? <p>{t('common.filteredEmpty')}</p> : null}{children}
  </>;
}
