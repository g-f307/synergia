import AxeBuilder from '@axe-core/playwright';
import { expect, Page, test, TestInfo } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { executionAggregate } from '../src/testing/execution-fixtures';
import { completeQuantityCoverage } from '../src/testing/indicator-fixtures';
import type { Indicators } from '../src/app/shared/api/operational.models';

const apiOrigin = `http://127.0.0.1:${process.env.E2E_API_PORT ?? '8000'}`;
const webOrigin = `http://127.0.0.1:${process.env.E2E_WEB_PORT ?? '4200'}`;
const organization = '19600000-0000-4000-8000-000000000001';
const organizationB = '19600000-0000-4000-8000-000000000002';
const period = { started_from: '2026-10-01T04:00:00Z', started_to: '2026-10-06T03:59:59.999999Z' };
const dashboardUrl = '/dashboard?' + new URLSearchParams({ organization_id: organization, date_from:period.started_from, date_to:period.started_to });

// Synthetic browser contracts complement the real PostgreSQL and authorization
// tests. Historical values deliberately differ from the current selection.
async function contracts(page: Page, options: { empty?: boolean; restricted?: boolean; locale?: string } = {}): Promise<void> {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const coverage = completeQuantityCoverage({planned:4,produced:0,received:0,released:0});
  coverage.planned = {known_sum:4,known_count:2,total_count:3,coverage_percent:200/3,state:'partial'};
  coverage.received = {known_sum:null,known_count:0,total_count:3,coverage_percent:0,state:'missing'};
  if (options.empty) for (const key of Object.keys(coverage) as Array<keyof typeof coverage>) {
    coverage[key] = {known_sum:null,known_count:0,total_count:0,coverage_percent:null,state:'empty'};
  }
  const indicators: Indicators = {
    generated_at:'2026-10-05T12:00:00Z',source:'synergia.operational',
    organizations:[{id:organization,code:'SYN',name:'Organização sintética A'}],
    filters:{organization_id:options.restricted?null:organization,date_from:period.started_from,date_to:period.started_to},
    executions:{completed:4},execution_summary:executionAggregate({completed:4},{scope:{permission:'dashboard.read',organization_ids:options.restricted?[organization,organizationB]:[organization]}}),
    workorders:{total:999,partially_released:999},quantities:{planned:999,produced:999,received:999,released:999},
    workorders_current:{total:options.empty?0:3,partially_released:0},quantities_coverage:coverage,pending_items:{open:0}
  };
  Object.assign(indicators.execution_summary.filters, indicators.filters);
  await page.route(`${apiOrigin}/**`, async route => {
    const request = route.request(); const url = new URL(request.url());
    const headers = {'access-control-allow-origin':webOrigin,'access-control-allow-credentials':'true','access-control-allow-headers':'authorization,content-type','x-correlation-id':'synthetic-196'};
    const json = (body: unknown, status = 200) => route.fulfill({status,headers,contentType:'application/json',body:JSON.stringify(body)});
    if (request.method()==='OPTIONS') { await route.fulfill({status:204,headers}); return; }
    if (url.pathname==='/auth/refresh') { await json({access_token:'synthetic-token',token_type:'Bearer',expires_in:3600,session_id:'synthetic-session'}); return; }
    if (url.pathname==='/me') { await json({id:'synthetic-user',status:'active',display_name:'Gestor sintético',emails:[],locale:options.locale??'pt-BR',timezone:'America/Manaus',notifications:{email:false,in_app:false},appearance:{density:'comfortable',font_scale:'normal'},avatar:null,permissions:[{key:'dashboard.read',organizations:options.restricted?[organization,organizationB]:[organization]},{key:'business.read',organizations:[organization]}],version:1}); return; }
    if (url.pathname==='/notifications/unread-count') { await json({count:0}); return; }
    if (url.pathname==='/indicators') { await json(indicators); return; }
    if (url.pathname==='/indicators/workorders') {
      expect(url.searchParams.get('view')).toBe('current');
      expect(url.searchParams.get('started_from')).toBe(period.started_from);
      expect(url.searchParams.get('started_to')).toBe(period.started_to);
      const count = options.empty?0:options.restricted?1:3;
      await json({entity:'workorders',view:'current',scope:{permissions:['dashboard.read','business.read'],organization_ids:[organization]},pagination:{page:1,pages:count?1:0,total:count},items:Array.from({length:count},(_,index)=>({identifier:`WO-00${index+1}`,status:'consolidated',execution_id:`execution-${index+1}`,organization_id:organization,organization_name:'Organização sintética A',snapshot_id:index+1,occurred_at:'2026-10-03T12:00:00Z',updated_at:'2026-10-04T12:00:00Z'}))}); return;
    }
    await json({code:'resource_not_found',message:'Synthetic missing resource'},404);
  });
}

async function evidence(page: Page, info: TestInfo, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  const audit = await new AxeBuilder({page}).analyze();
  await info.attach(`axe-${name}`,{body:JSON.stringify(audit.violations),contentType:'application/json'});
  expect(audit.violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  const screenshot=info.outputPath(`${name}.png`);
  await page.screenshot({path:screenshot});
  await info.attach(name,{path:screenshot,contentType:'image/png'});
}

for (const width of [390,768,1440]) for (const theme of ['light','dark']) {
  test(`coverage and reconciled current list at ${width}px ${theme}`,async({page},info)=>{
    await contracts(page); await page.setViewportSize({width,height:960}); await page.goto(dashboardUrl);
    await expect(page.locator('.indicator-value').nth(1)).toHaveText('3');
    if(theme==='dark') await page.locator('.theme-button').click();
    const planned=page.locator('[data-quantity="planned"]');
    await planned.scrollIntoViewIfNeeded();
    await expect(planned).toContainText('Subtotal conhecido');
    await expect(planned).toContainText('Dados de 2 de 3 Workorders');
    await expect(planned).toContainText('66,7%');
    await expect(planned.locator('.known-quantity')).toHaveText('4');
    await expect(page.getByRole('heading',{name:'Quantidades e cobertura'})).toBeVisible();
    await expect(page.locator('[data-quantity="produced"] .known-quantity')).toHaveText('0');
    await expect(page.locator('[data-quantity="received"]')).toContainText('Não informado');
    await expect(page.locator('[data-quantity="received"] [role="meter"]')).toHaveCount(0);
    await evidence(page,info,`coverage-${width}-${theme}`);
    const link=page.getByRole('link',{name:'Ver Workorders',exact:true});
    await link.focus(); await expect(link).toBeFocused(); await page.keyboard.press('Enter');
    await expect(page.locator('.workorder-row')).toHaveCount(3);
    const url=new URL(page.url());
    expect(url.searchParams.get('view')).toBe('current');
    expect(url.searchParams.get('organization_id')).toBe(organization);
    expect(url.searchParams.get('date_to')).toBe(period.started_to);
    const target=new URL(await page.locator('.workorder-row').first().getAttribute('href')??'',webOrigin);
    expect(target.searchParams.get('execution_id')).toBe('execution-1');
    expect(target.searchParams.get('organization_id')).toBe(organization);
    await evidence(page,info,`current-list-${width}-${theme}`);
    await page.reload(); await expect(page.locator('.workorder-row')).toHaveCount(3);
  });
}

test('empty and narrower detail scope remain explicit',async({page})=>{
  await contracts(page,{empty:true}); await page.goto(dashboardUrl);
  await expect(page.locator('.quantities-chart')).toContainText('Sem Workorders no período');
  await expect(page.locator('.quantities-chart [role="meter"]')).toHaveCount(0);
  await expect(page.locator('.quantities-chart .known-quantity')).toHaveCount(0);
  await page.unroute(`${apiOrigin}/**`); await contracts(page,{restricted:true});
  await page.goto('/dashboard?'+new URLSearchParams({date_from:period.started_from,date_to:period.started_to}));
  await expect(page.locator('.indicator-value').nth(1)).toHaveText('3');
  await expect(page.locator('.detail-scope-note')).toContainText('escopo de acesso mais restrito');
  await page.getByRole('link',{name:'Ver Workorders autorizadas'}).click();
  await expect(page.locator('.workorder-row')).toHaveCount(1);
  await expect(page.locator('.scope-note')).toContainText('Organizações no escopo dos detalhes: 1');
});

test('English coverage labels and decimal separator',async({page})=>{
  await contracts(page,{locale:'en-US'}); await page.goto(dashboardUrl);
  const planned=page.locator('[data-quantity="planned"]');
  await expect(planned).toContainText('66.7%');
  await expect(planned).toContainText('Known subtotal');
});

test('native zoom 250% preserves coverage and current list in both themes',async({playwright},info)=>{
  test.skip(process.env.E2E_NATIVE_ZOOM!=='true','Opt-in: Chromium extension support required.');
  test.setTimeout(90_000);
  const profile=await mkdtemp(path.join(tmpdir(),'synergia-196-zoom-'));
  const extension=path.join(info.project.testDir,'support/native-zoom');
  const context=await playwright.chromium.launchPersistentContext(profile,{
    headless:true,viewport:{width:1440,height:1000},executablePath:process.env.E2E_BROWSER_EXECUTABLE_PATH,
    args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]
  });
  try {
    const page=context.pages()[0]; await contracts(page); await page.goto(webOrigin+dashboardUrl);
    await expect(page.locator('.indicator-value').nth(1)).toHaveText('3');
    const worker=context.serviceWorkers()[0]??await context.waitForEvent('serviceworker');
    const zoom=await worker.evaluate(async()=>{
      const api=(globalThis as unknown as {chrome:{tabs:{query(query:{active:boolean}):Promise<Array<{id:number}>>;setZoom(id:number,factor:number):Promise<void>;getZoom(id:number):Promise<number>}}}).chrome;
      const [tab]=await api.tabs.query({active:true}); await api.tabs.setZoom(tab.id,2.5); return api.tabs.getZoom(tab.id);
    });
    expect(zoom).toBe(2.5);
    await expect.poll(()=>page.evaluate(()=>devicePixelRatio)).toBe(2.5);
    await info.attach('native-zoom',{body:JSON.stringify({factor:zoom,...await page.evaluate(()=>({innerWidth,devicePixelRatio}))}),contentType:'application/json'});
    for(const theme of ['light','dark']){
      await page.goto(webOrigin+dashboardUrl);
      await expect(page.locator('.indicator-value').nth(1)).toHaveText('3');
      if(await page.locator('html').getAttribute('data-theme')!==theme) await page.locator('.theme-button').click();
      await page.locator('[data-quantity="planned"]').scrollIntoViewIfNeeded();
      await evidence(page,info,`coverage-zoom250-${theme}`);
      await page.getByRole('link',{name:'Ver Workorders',exact:true}).click();
      await expect(page.locator('.workorder-row')).toHaveCount(3);
      await evidence(page,info,`current-list-zoom250-${theme}`);
    }
  } finally { await context.close(); await rm(profile,{recursive:true,force:true}); }
});
