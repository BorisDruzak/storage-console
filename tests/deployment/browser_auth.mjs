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
  console.log('Real browser TLS rejection/trust/login/reload/cross-tab logout/session rejection/mobile: PASS');
} catch (error) {
  // Never print Playwright call logs: form actions can contain the input password.
  const code = String(error?.message).match(/net::ERR_[A-Z_]+|ENOTFOUND|EAI_AGAIN/)?.[0] ?? 'assertion';
  console.log('BROWSER_AUTH_ACCEPTANCE_FAILED:' + phase + ':' + code);
  process.exitCode = 1;
} finally {
  await browser?.close();
  rmSync(home, { recursive: true, force: true });
}
