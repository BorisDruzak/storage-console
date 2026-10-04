import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { registerSource, type CreateSource, type SourceRegistration } from './client';
import { useControlRequest } from './useControlRequest';

export function SourceRegistrationForm({ onCreated, onPermissionDenied, onUnconfirmed }: {
  onCreated: (source: SourceRegistration) => void; onPermissionDenied?: () => void; onUnconfirmed?: () => void;
}) {
  const { t } = useTranslation(); const request = useControlRequest(onPermissionDenied, onUnconfirmed);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    const source: CreateSource = {
      source_type: String(data.get('source_type')) as CreateSource['source_type'],
      hostname: String(data.get('hostname')), instance_id: String(data.get('instance_id')),
      fqdn: String(data.get('fqdn')) || null, expected_cadence_seconds: Number(data.get('cadence')),
    };
    void request.run(signal => registerSource(source, signal), onCreated);
  }
  return <section className="source-controls"><h2>{t('sourceControl.registration')}</h2>
    <p>{t('sourceControl.identityHelp')}</p>
    {request.error ? <p role="alert">{t(`sourceControl.errors.${request.error}`)}</p> : null}
    <form onSubmit={submit}>
      <fieldset disabled={request.pending}><div className="control-fields">
        <label>{t('sourceControl.sourceType')}<select name="source_type" defaultValue="FILESERVER">{(['FILESERVER', 'PVE', 'PBS'] as const).map(type => <option key={type} value={type}>{t(`sourceTypes.${type}`)}</option>)}</select></label>
        <label>{t('sourceControl.hostname')}<input name="hostname" required maxLength={255} autoComplete="off" /></label>
        <label>{t('sourceControl.fqdn')}<input name="fqdn" maxLength={255} autoComplete="off" /></label>
        <label>{t('sourceControl.instance')}<input name="instance_id" required maxLength={255} autoComplete="off" /></label>
        <label>{t('sourceControl.cadence')}<input name="cadence" type="number" min={1} max={86400} step={1} defaultValue={60} required /></label>
      </div><button type="submit">{t('sourceControl.register')}</button></fieldset>
    </form>
    {request.pending ? <p role="status">{t('sourceControl.pending')}</p> : null}
  </section>;
}
