import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useExpiredEvidence } from '../api/evidence';
import { ReadState, timestamp } from '../components/ReadState';
import { RawValue } from '../components/RawValue';
import { directoryStream } from './client';

export function DirectoryStatus({ source }: { source: string }) {
  const { t, i18n } = useTranslation();
  const query = useQuery({ queryKey: ['directory-stream', source], queryFn: ({ signal }) => directoryStream(source, signal),
    retry: false, refetchInterval: 10000, gcTime: 0 });
  const expired = useExpiredEvidence(query.data);
  const data = query.data;
  const state = data?.state === 'CURRENT' && expired ? 'STALE' : data?.state;
  // Expiry changes CURRENT to STALE locally; keep that status visible.
  return <section><h3>{t('directoryNames.stream')}</h3><ReadState query={{...query, data: undefined}}>{data ? <>
    <p role="status">{t(`directoryNames.states.${state ?? 'UNKNOWN'}`)}</p>
    <dl><dt>{t('directoryNames.userCount')}</dt><dd><RawValue value={data.user_count == null ? null : String(data.user_count)} /></dd>
      <dt>{t('directoryNames.observedAt')}</dt><dd>{timestamp(data.observed_at ?? null, i18n.language) ?? t('common.unavailable')}</dd>
    </dl><p>{t('directoryNames.accountBoundary')}</p>
  </> : null}</ReadState></section>;
}
