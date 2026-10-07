import type { TFunction } from 'i18next';

const units = ['bytes.B', 'bytes.KiB', 'bytes.MiB', 'bytes.GiB', 'bytes.TiB'] as const;
export function formatBytes(value: number | null, locale: string, t: TFunction): string {
  if (value === null || !Number.isFinite(value) || value < 0) return t('common.unavailable');
  const index = value === 0 ? 0 : Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value / 1024 ** index)} ${t(units[index])}`;
}
