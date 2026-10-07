import { expect, test } from 'vitest';
import { createI18n } from './i18n';
import { formatBytes } from './formatBytes';

test('shared IEC formatter localizes number and unit, preserving zero and missing values',async()=>{
  const ru=await createI18n();
  expect(formatBytes(0,'ru-RU',ru.t)).toBe('0 Б');
  expect(formatBytes(1536,'ru-RU',ru.t)).toBe('1,5 КиБ');
  expect(formatBytes(1048576,'ru-RU',ru.t)).toBe('1 МиБ');
  expect(formatBytes(1073741824,'ru-RU',ru.t)).toBe('1 ГиБ');
  expect(formatBytes(1099511627776,'ru-RU',ru.t)).toBe('1 ТиБ');
  expect(formatBytes(null,'ru-RU',ru.t)).toBe('Не определено');
  const en=await createI18n('en-US');
  expect(formatBytes(1536,'en-US',en.t)).toBe('1.5 KiB');
});
