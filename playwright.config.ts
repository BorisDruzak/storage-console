import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  use: { baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173', locale: 'ru-RU', trace: 'retain-on-failure' },
  webServer: process.env.PLAYWRIGHT_BASE_URL ? undefined : { command: 'npm run dev --workspace apps/web -- --port 5173', url: 'http://127.0.0.1:5173', reuseExistingServer: false },
  reporter: [['list'], ['html', { open: 'never' }]],
});
