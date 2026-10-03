import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/ready', route => route.fulfill({contentType:'application/json',body:'{"status":"ok"}'}));
  await page.route('**/api/v1/**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(route.request().url().includes('/overview') ? { evaluated_at: '2026-10-04T00:00:00Z', counts: {sources:0,volumes:0,shares:0,filesystem_objects:0}, domains: [] } : {items:[],total:0,limit:50,offset:0}) }));
});

test('Russian shell retains unknown storage health across navigation', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('lang', 'ru-RU');
  await expect(page.getByRole('heading', { name: 'Обзор', exact: true })).toBeVisible();
  await expect(page.getByText('Нет данных', { exact: true }).first()).toBeVisible();
  await page.getByRole('link', { name: 'Источники данных', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Источники данных', exact: true })).toBeVisible();
  await expect(page.getByText('Исправно', { exact: true })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('API failure can be retried without losing the Russian shell', async ({ page }) => {
  await page.route('**/ready', route => route.fulfill({ status: 503, body: '{"status":"unavailable"}', contentType: 'application/json' }));
  await page.goto('/');
  await expect(page.getByText('API недоступен', { exact: true })).toBeVisible();
  await page.route('**/ready', route => route.fulfill({ status: 200, body: '{"status":"ok"}', contentType: 'application/json' }));
  await page.getByRole('button', { name: 'Повторить', exact: true }).first().click();
  await expect(page.getByText('API доступен', { exact: true })).toBeVisible();
});

test('deep links, tab filters and browser back restore the same view', async ({ page }) => {
  await page.goto('/#health?tab=volumes&source_id=6a83a99d-247d-4e58-8c49-089c703ab42d');
  await expect(page.getByRole('heading', {name:'Состояние хранилища',exact:true})).toBeVisible();
  await expect(page.getByLabel('Идентификатор источника')).toHaveValue('6a83a99d-247d-4e58-8c49-089c703ab42d');
  await page.getByLabel('Идентификатор источника').fill('6a83a99d-247d-4e58-8c49-089c703ab42e');
  await page.getByRole('button', {name:'Применить'}).click();
  await expect(page).toHaveURL(/source_id=6a83a99d-247d-4e58-8c49-089c703ab42e/);
  await page.goBack();
  await expect(page.getByLabel('Идентификатор источника')).toHaveValue('6a83a99d-247d-4e58-8c49-089c703ab42d');
});

test('overview remains usable on desktop and mobile without overflow', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const [width,height] of [[1280,900],[390,844]]) {
    await page.setViewportSize({width,height});
    await page.goto('/');
    await expect(page.getByRole('heading', {name:'Ёмкость',exact:true})).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({path:testInfo.outputPath(`overview-${width}.png`),fullPage:true});
  }
  expect(errors).toEqual([]);
});
