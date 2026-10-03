import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ESLint } from 'eslint';

test('i18n gate rejects JSX text, expressions and user-visible attributes', async () => {
  const eslint = new ESLint({ cwd: `${process.cwd()}/apps/web` });
  for (const code of [
    'export const Probe = () => <button>Untranslated</button>',
    "export const Probe = () => <button>{'Untranslated'}</button>",
    'export const Probe = () => <input placeholder="Untranslated" />',
    'export const Probe = () => <button title="Untranslated" />',
    'export const Probe = () => <button aria-label="Untranslated" />',
  ]) {
    const [result] = await eslint.lintText(code, { filePath: 'src/probe.tsx' });
    assert.ok(result.messages.some(message => message.ruleId === 'i18next/no-literal-string'), code);
  }
});
