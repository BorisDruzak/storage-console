// Real Windows metadata already ingested into a disposable HTTPS/API/PostgreSQL stack.
// Private session credentials arrive through stdin. No route interception or TLS bypass.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium, expect } from '@playwright/test';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const { origin, username, password, sourceId, expectedObjects } = JSON.parse(input);
input = '';
const home = mkdtempSync(join(tmpdir(), 'storage-pilot-browser-'));
let browser;
let phase = 'tls';
try {
  const db = join(home, '.pki', 'nssdb');
  mkdirSync(db, { recursive: true });
  execFileSync('certutil', ['-N', '-d', 'sql:' + db, '--empty-password']);
  execFileSync('certutil', ['-A', '-d', 'sql:' + db, '-n', 'Disposable pilot CA', '-t', 'C,,', '-i', '/fixture/ca.pem']);
  browser = await chromium.launch({ env: { ...process.env, HOME: home }, args: ['--host-resolver-rules=MAP storage.example.test 127.0.0.1', '--no-proxy-server'] });
  const context = await browser.newContext({ ignoreHTTPSErrors: false, locale: 'ru-RU' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.name));
  await page.goto(origin);
  phase = 'login';
  await page.locator('select[name="provider"]').selectOption('local');
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await expect(page.locator('.session-bar')).toContainText(username);
  const read = path => page.evaluate(async route => {
    const response = await fetch(route, { cache: 'no-store' });
    if (response.status !== 200) throw new Error('READ_FAILED');
    return response.json();
  }, path);
  phase = 'overview';
  const overview = await read('/api/v1/overview');
  assert.equal(overview.counts.sources, 1);
  assert.equal(overview.counts.volumes, 1);
  assert.equal(overview.counts.filesystem_objects, expectedObjects);
  await expect(page.getByText(`Источники: ${overview.counts.sources}`, { exact: true })).toBeVisible();
  await expect(page.getByText(`Тома: ${overview.counts.volumes}`, { exact: true })).toBeVisible();
  await expect(page.getByText(`Объекты файловой системы: ${expectedObjects}`, { exact: true })).toBeVisible();
  phase = 'source-freshness';
  await page.getByRole('link', { name: 'Источники данных', exact: true }).click();
  await page.getByRole('link', { name: 'synthetic-live-fileserver', exact: true }).click();
  const source = await read('/api/v1/sources/' + sourceId);
  assert.equal(source.freshness.state, 'HEALTHY');
  assert.ok(source.freshness.last_collector_at);
  assert.equal(source.freshness.collector_count, 1);
  await expect(page.getByText('Исправно', { exact: true }).first()).toBeVisible();
  phase = 'volume';
  await page.getByRole('link', { name: 'Тома', exact: true }).click();
  const volume = (await read('/api/v1/volumes?source_id=' + sourceId)).items[0];
  assert.ok(volume.unique_identity.startsWith('volume:'));
  assert.ok(volume.total_bytes > 0);
  await expect(page.getByText(volume.unique_identity, { exact: true }).last()).toBeVisible();
  await expect(page.getByText(volume.filesystem, { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText(volume.filesystem, { exact: true })).toBeVisible();
  phase = 'shares';
  await page.getByRole('link', { name: 'Общие папки SMB', exact: true }).click();
  assert.equal((await read('/api/v1/shares?source_id=' + sourceId)).total, 0);
  assert.deepEqual(errors, []);
  console.log('WINDOWS_PILOT_BROWSER_PASS: sources=1 volumes=1 objects=' + expectedObjects + ' shares=0 reload=PASS TLS=verified');
} catch {
  console.log('WINDOWS_PILOT_BROWSER_FAILED: ' + phase);
  process.exitCode = 1;
} finally {
  await browser?.close();
  rmSync(home, { recursive: true, force: true });
}
