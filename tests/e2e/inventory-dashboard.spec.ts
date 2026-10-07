import { expect, test } from '@playwright/test';

const stamp='2026-10-07T10:00:00Z';
const overview={overall_state:'UNKNOWN',evaluated_at:stamp,domains:['TELEMETRY','CAPACITY','FILESYSTEM','SMB_DFS','ACCESS','VSS','RECOVERY','NETWORK','PVE_ZFS','HYGIENE'].map(domain=>({domain,state:'UNKNOWN',source_count:1,covered_source_count:0,unknown_source_count:1})),counts:{sources:1,volumes:1,shares:0,filesystem_objects:42},freshness:{state:'HEALTHY',source_count:1,current_source_count:1,stale_source_count:0,unknown_source_count:0,last_received_at:stamp,oldest_event_at:stamp},capacity:{state:'OBSERVE',total_bytes:1099511627776,used_bytes:824633720832,free_bytes:274877906944,used_percent:75,volume_count:1,current_volume_count:1,unavailable_volume_count:0,latest_inventory_at:stamp},inventory:{latest_inventory_at:stamp,volume_count:1,filesystem_types:['NTFS'],filesystem_objects:42}};
test('current inventory overview, IEC volumes, reload and saved UTC on desktop and mobile',async({page},testInfo)=>{
  const errors:string[]=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error') errors.push(message.text());});
  await page.route('**/ready',route=>route.fulfill({json:{status:'ok'}}));
  await page.route('**/api/v1/**',route=>{
    const url=route.request().url();
    const data=url.includes('/auth/me')?{id:'6a83a99d-247d-4e58-8c49-089c703ab42d',username:'synthetic-viewer',roles:['viewer']}:
      url.includes('/overview')?overview:
      {items:[{id:'6a83a99d-247d-4e58-8c49-089c703ab42d',source_node_id:'6a83a99d-247d-4e58-8c49-089c703ab42e',unique_identity:'synthetic-volume',filesystem:'NTFS',label:'synthetic-DATA',mount_aliases:['X:'],total_bytes:1099511627776,free_bytes:274877906944,quality:'COMPLETE',first_seen_at:stamp,last_seen_at:stamp}],total:1,limit:50,offset:0};
    return route.fulfill({headers:{'X-Evidence-Valid-For-Ms':'35000','Cache-Control':'no-store'},json:data});
  });
  for(const [width,height] of [[1280,900],[390,844]]) {
    await page.setViewportSize({width,height});
    await page.goto('/');
    await expect(page).toHaveTitle('Storage Console');
    const capacity=page.locator('article').filter({has:page.getByRole('heading',{name:'Ёмкость',exact:true})});
    await expect(capacity).toContainText('Использовано: 768 ГиБ');
    await expect(capacity).toContainText('Наблюдение');
    const filesystem=page.locator('article').filter({has:page.getByRole('heading',{name:'Файловая система NTFS',exact:true})});
    await expect(filesystem).toContainText('Нет данных');
    await expect(filesystem).toContainText('15:00:00 GMT+5');
    await expect(filesystem).toContainText('Данные о целостности файловой системы ещё не собираются');
    await expect(page.getByText('Объекты файловой системы: 42',{exact:true})).toBeVisible();
    await expect(page.getByText('UNKNOWN',{exact:true})).toHaveCount(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:testInfo.outputPath(`inventory-overview-${width}.png`),fullPage:true});
    await page.reload();
    await expect(capacity).toContainText('Свободно: 256 ГиБ');
    await page.getByRole('link',{name:'Состояние хранилища',exact:true}).click();
    await page.getByRole('link',{name:'Тома',exact:true}).click();
    await expect(page.locator('tbody')).toContainText('1 ТиБ');
    await expect(page.locator('tbody')).toContainText('256 ГиБ');
    await expect(page.locator('tbody')).toContainText('Полные данные');
    await expect(page.locator('tbody')).toContainText('NTFS');
    await expect(page.locator('tbody')).toContainText('X:');
    await page.screenshot({path:testInfo.outputPath(`inventory-volumes-${width}.png`),fullPage:true});
  }
  await page.getByRole('link',{name:'Настройки',exact:true}).click();
  await expect(page.getByLabel('Часовой пояс')).toHaveValue('Asia/Yekaterinburg');
  await page.getByLabel('Часовой пояс').fill('UTC');
  await page.getByRole('button',{name:'Сохранить настройки'}).click();
  await page.reload();
  await expect(page.getByLabel('Часовой пояс')).toHaveValue('UTC');
  await page.getByRole('link',{name:'Обзор',exact:true}).click();
  await expect(page.locator('article').filter({has:page.getByRole('heading',{name:'Файловая система NTFS',exact:true})})).toContainText('10:00:00 UTC');
  expect(errors).toEqual([]);
});
