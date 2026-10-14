import { expect, test } from '@playwright/test';

const id = '00000000-0000-0000-0000-000000000001';
const time = '2026-10-13T00:00:00Z';
const evidence = { id, source_id: id, audit_collector_id: id, first_received_at: time, digest: 'a'.repeat(64),
  numeric_fields: { record_id: '10', logon_id: '257', handle_id: '49', process_id: '64', access_mask: '65536' },
  evidence: { host_id: id, boot_id: 'synthetic-boot', generation: id, channel: 'Security', record_id: 10,
    provider: '54849625-5478-4994-a5ba-3e3b0328c30d', event_id: 4663, version: 0, occurred_at: time,
    account: 'SyntheticUserA', domain: 'SYNTHETIC', sid: 'S-1-5-21-100-200-300-1001', logon_id: 257,
    handle_id: 49, process_id: 64, access_mask: 65536, object_type: 'File', path: String.raw`C:\Pilot\Отчёт.txt`,
    volume_id: 'volume-a', quality: 'COMPLETE', path_quality: 'UNKNOWN', linked_record_ids: [] } };
const verdict = { change_id: id, object_id: null, classification: 'CORRELATED_HIGH', reason: 'UNIQUE_DELETE_CHAIN',
  rule_version: 'windows-security-usn-v1', actor: { sid: evidence.evidence.sid, account: 'SyntheticUserA',
    domain: 'SYNTHETIC', logon_id: '257', host_id: id, boot_id: 'synthetic-boot', client_ip: null,
    workstation: null, identity_evidence_id: id }, candidates: [{ method: 'SCOPED_SECURITY_USN',
    classification: 'CORRELATED_HIGH', reason: 'UNIQUE_DELETE_CHAIN', rule_version: 'windows-security-usn-v1', evidence }],
  stream: { state: 'NOT_CONFIGURED', evaluated_at: time } };
const accountObservation = {state:'CURRENT', observed_at:time, snapshot_id:id,
  latest_attempt_state:'COMPLETE', valid_for_ms:900000, user:{
    sid:evidence.evidence.sid, object_guid:id, account:'CurrentDirectoryName',
    upn:'current@example.test', display_name:'Тестовый сотрудник', enabled:false, primary_group_id:513}};
const clientObservation = {state:'CONFIRMED_CURRENT', observed_at:time,
  expires_at:'2026-10-13T00:15:00Z', computer_name:'SyntheticClientPC', ptr_name:'pc.example.test',
  computer_sid:'S-1-5-21-100-200-300-1002', computer_guid:id,
  reason:null, event_time_confirmed:false, valid_for_ms:900000};

test('admin audit evidence, private POST filters, mobile and reload', async ({ page, context }, testInfo) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await context.addCookies([{ name: '__Host-storage_csrf', value: 'a'.repeat(43), domain: '127.0.0.1', path: '/', secure: true }]);
  let searched = false;
  await page.route('**/api/v1/**', async route => {
    const url = route.request().url();
    let body: object = { detail: 'UNAVAILABLE' };
    if (url.includes('/auth/me')) body = { id, username: 'synthetic-admin', roles: ['storage_admin'] };
    else if (url.includes('/audit/changes/')) body = {...verdict,
      actor:{...verdict.actor, account_observation:accountObservation, client_observation:clientObservation}};
    else if (url.includes('/audit/search')) {
      expect(route.request().method()).toBe('POST'); expect(url).not.toContain('SyntheticUserA');
      expect(route.request().postDataJSON()).toMatchObject({ account: 'SyntheticUserA' });
      expect(route.request().headers()['x-csrf-token']).toBe('a'.repeat(43)); searched = true;
      body = { items: [evidence], limit: 50, offset: 0, has_more: false, evaluated_at: time };
    } else if (url.includes('/activity')) body = { items: [{ id, source_id: id, object_id: null,
      volume_identity: 'volume-a', file_id: 'file-a', parent_file_id: null, occurred_at: time,
      event_type: 'DELETE', old_relative_path: 'Pilot/Отчёт.txt', new_relative_path: null,
      reason_mask: '0x200', source_event_id: 'ntfs-usn:'+'a'.repeat(64), provenance: 'NTFS_USN',
      path_quality: 'COMPLETE', actor: null, client: null, confidence: null }], total: 1, limit: 50, offset: 0,
      evaluated_at: time, quality: 'COMPLETE', continuity: 'UNKNOWN', window_start_at: '2026-10-12T00:00:00Z', window_end_at: time };
    await route.fulfill({ contentType: 'application/json', headers: { 'X-Evidence-Valid-For-Ms': '35000', 'Cache-Control': 'no-store' }, body: JSON.stringify(body) });
  });
  await page.route('**/ready', route => route.fulfill({ json: { status: 'ok' } }));
  for (const [width, height] of [[1280, 900], [390, 844]]) {
    await page.setViewportSize({ width, height }); await page.goto('/#activity');
    await page.getByRole('button', { name: 'Подтверждения показанного события' }).click();
    await expect(page.getByText('Обоснованная атрибуция', { exact: true })).toBeVisible();
    await expect(page.getByText('Событие 4663, RecordID 10')).toBeVisible();
    await expect(page.getByText('SyntheticUserA').first()).toBeVisible();
    await expect(page.getByText('CurrentDirectoryName', {exact:true})).toBeVisible();
    await expect(page.getByText('SyntheticClientPC', {exact:true})).toBeVisible();
    await expect(page.getByText('Учётная запись использовала право доступа к объекту.', { exact: false }).first()).toBeVisible();
    await page.getByLabel('Учётная запись', { exact: true }).fill('SyntheticUserA');
    await page.getByRole('button', { name: 'Найти свидетельства' }).click();
    await expect(page.getByText('Событие 4663, RecordID 10')).toHaveCount(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`audit-${width}.png`), fullPage: true });
    await page.reload();
    await expect(page.getByRole('button', { name: 'Подтверждения показанного события' })).toBeVisible();
    expect(page.url()).not.toContain('SyntheticUserA');
  }
  expect(searched).toBe(true); expect(errors).toEqual([]);
});

test('nonadmin deep link never requests sensitive activity or audit', async ({ page }) => {
  const sensitive: string[] = [];
  page.on('request', request => { if (/\/api\/v1\/(activity|audit\/)/.test(request.url())) sensitive.push(request.url()); });
  await page.route('**/api/v1/**', route => route.fulfill({ json: route.request().url().includes('/auth/me') ?
    { id, username: 'synthetic-viewer', roles: ['viewer'] } : { detail: 'UNAVAILABLE' } }));
  await page.route('**/ready', route => route.fulfill({json:{status:'ok'}}));
  await page.goto('/#activity');
  await expect(page.getByText('Чувствительная история и аудит доступны только администратору.')).toBeVisible();
  expect(sensitive).toEqual([]);
});
