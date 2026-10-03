import { expect, test } from 'vitest';
import { createI18n, validateCatalogs } from './i18n';

test('Russian is default and unsupported locales fall back to English', async () => {
  const ru = await createI18n();
  expect(ru.t('navigation.overview')).toBe('Обзор');
  const other = await createI18n('fr-FR');
  expect(other.t('navigation.overview')).toBe('Overview');
});

test('missing key in either catalog fails validation', () => {
  expect(() => validateCatalogs({ a: 'А' }, { a: 'A' })).not.toThrow();
  expect(() => validateCatalogs({ a: 'А' }, {})).toThrow('a');
  expect(() => validateCatalogs({}, { a: 'A' })).toThrow('a');
  expect(() => validateCatalogs({ a: '' }, { a: 'A' })).toThrow('a');
});
