import { useTranslation } from 'react-i18next';

export function RawValue({value}: {value:string | null}) {
  const {t}=useTranslation();
  if (value===null) return <span>{t('common.unavailable')}</span>;
  if (value.length<=120) return <code>{value}</code>;
  const preview=value.slice(0,64)+'…'+value.slice(-32);
  return <details className="raw-value"><summary>{t('common.showFullValue')}<code>{preview}</code></summary><code>{value}</code></details>;
}
