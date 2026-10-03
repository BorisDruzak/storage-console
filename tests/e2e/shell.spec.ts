import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/ready', route => route.fulfill({contentType:'application/json',body:'{"status":"ok"}'}));
  await page.route('**/api/v1/**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(route.request().url().includes('/overview') ? { overall_state: 'UNKNOWN', freshness: {state:'UNKNOWN',source_count:0,current_source_count:0,stale_source_count:0,unknown_source_count:0,last_received_at:null,oldest_event_at:null}, evaluated_at: '2026-10-04T00:00:00Z', counts: {sources:0,volumes:0,shares:0,filesystem_objects:0}, domains: [] } : {items:[],total:0,limit:50,offset:0}) }));
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

test('activity and recovery shells expose domain structure with unavailable evidence', async ({page})=>{
  await page.goto('/#activity');
  await expect(page.getByRole('columnheader',{name:'Достоверность'})).toBeVisible();
  await expect(page.getByText('Для этого раздела ещё нет данных источников')).toBeVisible();
  await page.getByRole('link',{name:'Восстановление',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Проверка восстановления'})).toBeVisible();
  await expect(page.getByText('Нет данных',{exact:true})).toHaveCount(9);
  await expect(page.getByText('Исправно',{exact:true})).toHaveCount(0);
});

test('test-only domain observations render event storm and independent recovery states',async({page},testInfo)=>{
  test.skip(!!process.env.PLAYWRIGHT_BASE_URL,'Synthetic fixture entry is excluded from production dist');
  const errors:string[]=[];
  page.on('pageerror',error=>errors.push(error.message));
  for(const [width,height] of [[1280,900],[390,844]]) {
    await page.setViewportSize({width,height});
    await page.goto('/test-fixtures/domains.html#activity');
    await expect(page.getByText('Событий в группе: 100')).toBeVisible();
    await expect(page.locator('tbody tr')).toHaveCount(1);
    expect((await page.locator('tbody tr').boundingBox())!.height).toBeLessThan(400);
    await expect(page.getByText('80 %')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:testInfo.outputPath(`activity-${width}.png`),fullPage:true});
    await page.locator('tbody details summary').first().click();
    await expect(page.locator('tbody details').first()).toHaveAttribute('open','');
    expect(await page.locator('tbody details[open] > code').textContent()).toContain('Длинный путь/'.repeat(20));
    await page.getByRole('link',{name:'Восстановление',exact:true}).click();
    await expect(page.getByText('Исправно',{exact:true})).toBeVisible();
    await expect(page.getByText('Не защищена',{exact:true})).toBeVisible();
    await expect(page.getByText('Нет данных',{exact:true})).toHaveCount(9);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:testInfo.outputPath(`recovery-${width}.png`),fullPage:true});
  }
  expect(errors).toEqual([]);
});

test('stale domain fixture suppresses current confidence and platform health',async({page})=>{
  test.skip(!!process.env.PLAYWRIGHT_BASE_URL,'Synthetic fixture entry is excluded from production dist');
  await page.goto('/test-fixtures/domains.html?stale=1#activity');
  await expect(page.getByText('Устаревшие данные',{exact:true})).toBeVisible();
  await expect(page.getByText('80 %')).toHaveCount(0);
  await page.getByRole('link',{name:'Восстановление',exact:true}).click();
  await expect(page.getByText('Устаревшие данные',{exact:true})).toBeVisible();
  await expect(page.getByText('Исправно',{exact:true})).toHaveCount(0);
  await expect(page.getByText('Не защищена',{exact:true})).toHaveCount(0);
});

test('remaining domain navigation exposes distinct Russian shells and preserves filters',async({page})=>{
  const views=[['access','Доступ и права','Ожидаемые права'],['hygiene','Гигиена данных','Классификация'],
    ['discovery','Поиск процессов','Семейство схемы'],['policies','Политики','Пороговые значения'],['audit','Журнал действий','Инициатор']];
  for(const [section,title,column] of views){
    await page.goto('/#'+section);
    await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
    await expect(page.getByRole('columnheader',{name:column,exact:true})).toBeVisible();
    await expect(page.getByText('Для этого раздела ещё нет данных источников')).toBeVisible();
  }
  await page.goto('/#diagnostics');
  for(const phase of ['До события','Событие','После события']) await expect(page.getByRole('region',{name:phase,exact:true})).toBeVisible();
  await page.goto('/#hygiene?category=LONG_PATH');
  await page.getByLabel('Идентификатор источника').fill('synthetic-source');
  await page.getByRole('button',{name:'Применить'}).click();
  await expect(page).toHaveURL(/category=LONG_PATH/);
  await expect(page).toHaveURL(/source_id=synthetic-source/);
  await page.goBack();
  await expect(page.getByLabel('Идентификатор источника')).toHaveValue('');
});

test('remaining domain fixtures render raw identities and translated conclusions on desktop and mobile',async({page},testInfo)=>{
  test.skip(!!process.env.PLAYWRIGHT_BASE_URL,'Synthetic fixture entry is excluded from production dist');
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  const views=[['access','Расхождение'],['hygiene','Кандидат'],['discovery','Одобрено'],['policies','synthetic-policy'],['audit','Приём данных']];
  for(const [width,height] of [[1280,900],[390,844]]){
    await page.setViewportSize({width,height});
    for(const [section,value] of views){
      await page.goto('/test-fixtures/domains.html#'+section);
      await expect(page.locator('tbody').getByText(value,{exact:true})).toBeVisible();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await page.screenshot({path:testInfo.outputPath(`${section}-${width}.png`),fullPage:true});
    }
    await page.goto('/test-fixtures/domains.html#diagnostics');
    await expect(page.getByRole('region',{name:'Событие',exact:true}).getByText('50',{exact:true})).toBeVisible();
    await page.screenshot({path:testInfo.outputPath(`diagnostics-${width}.png`),fullPage:true});
  }
  expect(errors).toEqual([]);
});
