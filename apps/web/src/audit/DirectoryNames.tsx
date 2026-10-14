import { useTranslation } from 'react-i18next';
import type { components } from '../api/generated';
import { useExpiredEvidence } from '../api/evidence';
import { RawValue } from '../components/RawValue';
import { timestamp } from '../components/ReadState';

type Models = components['schemas'];
type Props = { account?: Models['AccountObservation'] | null; client?: Models['ClientObservation'] | null };

export function DirectoryNames(props: Props) {
  return props.account || props.client ? <ObservedNames {...props} /> : null;
}

function ObservedNames({ account, client }: Props) {
  const { t, i18n } = useTranslation();
  const accountExpired = useExpiredEvidence(account);
  const clientExpired = useExpiredEvidence(client);
  const accountState = account?.state === 'CURRENT' && accountExpired ? 'STALE' : account?.state;
  const clientState = client?.state === 'CONFIRMED_CURRENT' && clientExpired ? 'STALE' : client?.state;
  return <aside className="directory-observations">
    {account ? <section><h5>{t('directoryNames.account')}</h5>
      <p role="status">{t(`directoryNames.states.${accountState ?? 'UNKNOWN'}`)}</p>
      {account.user ? <><dl>
        <dt>{t('directoryNames.accountName')}</dt><dd><RawValue value={account.user.account} /></dd>
        <dt>{t('directoryNames.displayName')}</dt><dd><RawValue value={account.user.display_name ?? null} /></dd>
        <dt>{t('directoryNames.upn')}</dt><dd><RawValue value={account.user.upn ?? null} /></dd>
        <dt>{t('directoryNames.observedAt')}</dt><dd>{timestamp(account.observed_at ?? null, i18n.language) ?? t('common.unavailable')}</dd>
      </dl>{account.user.enabled ? null : <p>{t('directoryNames.disabled')}</p>}</> : null}
      <p>{t('directoryNames.accountBoundary')}</p>
    </section> : null}
    {client ? <section><h5>{t('directoryNames.client')}</h5>
      <p role="status">{t(`directoryNames.states.${clientState ?? 'UNKNOWN'}`)}</p>
      <dl>
        <dt>{t('directoryNames.computer')}</dt><dd><RawValue value={client.computer_name ?? null} /></dd>
        <dt>{t('directoryNames.dnsName')}</dt><dd><RawValue value={client.ptr_name ?? null} /></dd>
        <dt>{t('directoryNames.observedAt')}</dt><dd>{timestamp(client.observed_at ?? null, i18n.language) ?? t('common.unavailable')}</dd>
        <dt>{t('directoryNames.expiresAt')}</dt><dd>{timestamp(client.expires_at ?? null, i18n.language) ?? t('common.unavailable')}</dd>
      </dl><p>{t('directoryNames.clientBoundary')}</p>
    </section> : null}
  </aside>;
}
