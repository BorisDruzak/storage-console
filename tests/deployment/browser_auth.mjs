// Disposable real TLS/API acceptance. Credentials arrive only through stdin.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium, expect } from '@playwright/test';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const { origin, username, password } = JSON.parse(input);
input = '';
const home = mkdtempSync(join(tmpdir(), 'storage-browser-'));
const launch = () => chromium.launch({
  env: { ...process.env, HOME: home },
  args: ['--host-resolver-rules=MAP storage.example.test 127.0.0.1', '--no-proxy-server'],
});
let browser;
let phase = 'untrusted-certificate';
async function sourceAcceptance(page) {
  phase = 'source-registration';
  await page.getByRole('link', { name: 'Источники данных', exact: true }).click();
  await page.getByLabel('Имя узла', { exact: true }).fill('synthetic-browser-source');
  await page.getByLabel('Идентификатор экземпляра', { exact: true }).fill('synthetic-browser-instance');
  await page.getByRole('button', { name: 'Зарегистрировать источник', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'synthetic-browser-source', exact: true })).toBeVisible();
  const sourceId = await page.evaluate(() => new URLSearchParams(location.hash.split('?')[1]).get('id'));
  const readFreshness = () => page.evaluate(async id => {
    const response = await fetch('/api/v1/sources/' + id, { cache: 'no-store' });
    if (response.status !== 200) return null;
    return (await response.json()).freshness;
  }, sourceId);
  assert.equal((await readFreshness()).state, 'UNKNOWN');
  phase = 'collector-enrollment-lost-response';
  // Discard one real successful response after the server commits. Do not
  // repeat issuance or inspect/store its lost credential.
  await page.evaluate(() => {
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
      if (typeof args[0] === 'string' && args[0].endsWith('/collectors') && args[1]?.method === 'POST') {
        window.fetch = originalFetch;
        const response = await originalFetch(...args);
        if (response.status === 201) throw new TypeError('Synthetic response loss');
        return response;
      }
      return originalFetch(...args);
    };
  });
  await page.getByRole('button', { name: 'Зарегистрировать collector', exact: true }).click();
  const key = page.getByLabel('Ключ collector', { exact: true });
  await expect(page.getByRole('alert')).toContainText('Результат операции не подтверждён');
  await expect(key).toHaveCount(0);
  await page.getByRole('button', { name: 'Обновить ключ', exact: true }).click();
  await expect(key).toBeVisible();
  let original = await key.inputValue();
  assert.match(original, /^[A-Za-z0-9_-]{43}$/);
  const collectorId = await page.evaluate(async id => {
    const response = await fetch('/api/v1/sources/' + id + '/collectors?limit=50&offset=0', { cache: 'no-store' });
    const metadata = await response.json();
    if (response.status !== 200 || metadata.items.length !== 1 || 'token' in metadata.items[0] || 'token_hash' in metadata.items[0]) return null;
    return metadata.items[0].id;
  }, sourceId);
  assert.ok(collectorId);
  await expect(page.getByRole('region', { name: 'Одноразовый показ ключа' })).toContainText(collectorId);
  const heartbeat = token => page.evaluate(async ({ token, collectorId }) => {
    const stamp = new Date().toISOString();
    return (await fetch('/api/v1/ingest/heartbeat', {
      method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
      body: JSON.stringify({ collector_id: collectorId, batch_id: crypto.randomUUID(), schema_version: 1,
        sent_at: stamp, first_event_at: stamp, last_event_at: stamp, record_count: 1,
        records: [{ occurred_at: stamp, version: 'synthetic-browser', cursor: '1', lag_seconds: 0 }] }),
    })).status;
  }, { token, collectorId });
  assert.equal(await heartbeat(original), 202);
  await page.getByRole('button', { name: 'Закрыть ключ', exact: true }).click();
  await expect(key).toHaveCount(0);
  phase = 'collector-rotation';
  await page.getByRole('button', { name: 'Обновить ключ', exact: true }).click();
  await expect(key).toBeVisible();
  let rotated = await key.inputValue();
  assert.notEqual(rotated, original);
  assert.equal(await heartbeat(original), 401);
  original = '';
  assert.equal(await heartbeat(rotated), 202);
  phase = 'collector-disable-reenable';
  await page.getByRole('button', { name: 'Отключить', exact: true }).click();
  await expect(key).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Включить', exact: true })).toBeEnabled();
  assert.equal(await heartbeat(rotated), 401);
  await page.getByRole('button', { name: 'Включить', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Отключить', exact: true })).toBeEnabled();
  assert.equal(await heartbeat(rotated), 202);
  rotated = '';
  assert.equal((await readFreshness()).state, 'HEALTHY');
  phase = 'collector-mobile-layout';
  await page.reload();
  await expect(page.getByRole('heading', { name: 'synthetic-browser-source', exact: true })).toBeVisible();
  await expect(key).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.locator('.source-controls').screenshot({ path: '/evidence/collectors-mobile.png' });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.locator('.source-controls').screenshot({ path: '/evidence/collectors-desktop.png' });
}
try {
  // First prove that the client rejects the untrusted fixture certificate.
  browser = await launch();
  const untrusted = await browser.newPage({ ignoreHTTPSErrors: false });
  await assert.rejects(untrusted.goto(origin), /ERR_CERT_AUTHORITY_INVALID/);
  await browser.close();
  browser = undefined;
  phase = 'install-disposable-trust';
  const db = join(home, '.pki', 'nssdb');
  mkdirSync(db, { recursive: true });
  execFileSync('certutil', ['-N', '-d', 'sql:' + db, '--empty-password']);
  execFileSync('certutil', ['-A', '-d', 'sql:' + db, '-n', 'Disposable storage CA', '-t', 'C,,', '-i', '/fixture/ca.pem']);
  browser = await launch();
  phase = 'trusted-navigation';
  const context = await browser.newContext({ ignoreHTTPSErrors: false, viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.name));
  await page.goto(origin);
  await expect(page.getByRole('heading', { name: 'Вход в Storage Console' })).toBeVisible();
  assert.equal(await page.evaluate(() => window.isSecureContext), true);
  const status = path => page.evaluate(async route => (await fetch(route, { cache: 'no-store' })).status, path);
  assert.equal(await status('/api/v1/overview'), 401);
  await page.screenshot({ path: '/evidence/login-desktop.png' });
  phase = 'local-login';
  await page.locator('select[name="provider"]').selectOption('local');
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await expect(page.locator('.session-bar')).toContainText(username);
  phase = 'authenticated-cookies-and-read';
  const cookies = await context.cookies();
  const session = cookies.find(cookie => cookie.name === '__Host-storage_session');
  assert.ok(session?.secure && session.httpOnly && session.sameSite === 'Lax');
  assert.equal(await status('/api/v1/overview'), 200);
  assert.equal(await page.evaluate(() => document.cookie.includes('__Host-storage_session=')), false);
  await page.reload();
  await expect(page.locator('.session-bar')).toContainText(username);
  await sourceAcceptance(page);
  await page.getByRole('link', { name: 'Обзор', exact: true }).click();
  phase = 'reload-and-second-tab';
  await expect(page.locator('.session-bar')).toContainText(username);
  await page.screenshot({ path: '/evidence/console-desktop.png' });
  const other = await context.newPage();
  await other.goto(origin);
  await expect(other.locator('.session-bar')).toContainText(username);
  phase = 'cross-tab-logout';
  await page.getByRole('button', { name: 'Выйти', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Вход в Storage Console' })).toBeVisible();
  await expect(other.getByRole('heading', { name: 'Вход в Storage Console' })).toBeVisible();
  assert.equal(await status('/api/v1/auth/me'), 401);
  phase = 'rejected-session-clears-console';
  await page.locator('select[name="provider"]').selectOption('local');
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await expect(page.locator('.session-bar')).toContainText(username);
  const current = (await context.cookies()).find(cookie => cookie.name === '__Host-storage_session');
  phase = 'rejected-session-cookie';
  assert.ok(current?.secure && current.httpOnly);
  await context.addCookies([{ ...current, value: 'a'.repeat(43) }]);
  phase = 'rejected-session-navigation';
  await page.getByRole('link', { name: 'Состояние хранилища', exact: true }).click();
  phase = 'rejected-session-primary-gate';
  await expect(page.getByRole('heading', { name: 'Вход в Storage Console' })).toBeVisible();
  phase = 'rejected-session-other-gate';
  await expect(other.getByRole('heading', { name: 'Вход в Storage Console' })).toBeVisible();
  assert.equal(await page.locator('.session-bar').count(), 0);
  phase = 'mobile-and-runtime-errors';
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  assert.equal(await page.locator('input[name="password"]').inputValue(), '');
  await page.screenshot({ path: '/evidence/login-mobile.png' });
  assert.deepEqual(errors, []);
  console.log('Real browser TLS/auth/source registration/enrollment/heartbeat/rotation/disable/re-enable/mobile: PASS');
} catch (error) {
  // Never print Playwright call logs: form actions can contain the input password.
  const code = String(error?.message).match(/net::ERR_[A-Z_]+|ENOTFOUND|EAI_AGAIN/)?.[0] ?? 'assertion';
  console.log('BROWSER_AUTH_ACCEPTANCE_FAILED:' + phase + ':' + code);
  process.exitCode = 1;
} finally {
  await browser?.close();
  rmSync(home, { recursive: true, force: true });
}
