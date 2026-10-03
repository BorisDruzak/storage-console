import { createInstance } from 'i18next';
import { initReactI18next } from 'react-i18next';
import ru from '../../../packages/i18n/ru-RU.json';
import en from '../../../packages/i18n/en-US.json';

function flatten(value: Record<string, unknown>, prefix = ''): Record<string, string> {
  return Object.fromEntries(Object.entries(value).flatMap(([key, item]) => {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    return typeof item === 'string' ? [[fullKey, item]] : Object.entries(flatten(item as Record<string, unknown>, fullKey));
  }));
}

export function validateCatalogs(a: Record<string, unknown>, b: Record<string, unknown>) {
  const left = flatten(a);
  const right = flatten(b);
  const invalid = [...new Set([...Object.keys(left), ...Object.keys(right)])]
    .filter(key => !left[key]?.trim() || !right[key]?.trim());
  if (invalid.length) throw new Error(`Missing translation keys: ${invalid.join(', ')}`);
}

export async function createI18n(locale = 'ru-RU') {
  validateCatalogs(ru, en);
  const instance = createInstance();
  await instance.use(initReactI18next).init({
    lng: locale, fallbackLng: 'en-US', supportedLngs: ['ru-RU', 'en-US'],
    resources: { 'ru-RU': { translation: ru }, 'en-US': { translation: en } },
    interpolation: { escapeValue: false },
  });
  return instance;
}
