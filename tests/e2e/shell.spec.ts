import { expect, test } from '@playwright/test';

test('Russian shell retains unknown storage health across navigation', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('lang', 'ru-RU');
  await expect(page.getByRole('heading', { name: 'Обзор', exact: true })).toBeVisible();
  await expect(page.getByText('Нет данных', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Источники данных', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Источники данных', exact: true })).toBeVisible();
  await expect(page.getByText('Исправно', { exact: true })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('API failure can be retried without losing the Russian shell', async ({ page }) => {
  await page.route('**/ready', route => route.fulfill({ status: 503, body: '{"status":"unavailable"}', contentType: 'application/json' }));
  await page.goto('/');
  await expect(page.getByText('API недоступен', { exact: true })).toBeVisible();
  await page.route('**/ready', route => route.fulfill({ status: 200, body: '{"status":"ok"}', contentType: 'application/json' }));
  await page.getByRole('button', { name: 'Повторить', exact: true }).click();
  await expect(page.getByText('API доступен', { exact: true })).toBeVisible();
});
