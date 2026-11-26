import { expect, Page, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';

const apiOrigin=`http://127.0.0.1:${process.env.E2E_API_PORT??'8000'}`;
const orgA='19600000-0000-4000-8000-000000000001';
const orgB='19600000-0000-4000-8000-000000000002';
const period={date_from:'2026-10-01T04:00:00Z',date_to:'2026-10-06T03:59:59.999999Z'};
const dashboard=(extra:Record<string,string>={})=>'/dashboard?'+new URLSearchParams({...period,...extra});
const python=process.env.E2E_PYTHON??'python';

test.beforeAll(()=>{
  execFileSync(python,['../scripts/bootstrap_indicator_coverage_e2e.py'],{env:{...process.env,SYNERGIA_ENV:'test'}});
});

async function login(page:Page,label='reader'){
  const email=`coverage-${label}.e2e@example.invalid`;
  execFileSync(python,['../scripts/bootstrap_web_e2e.py','--revoke-email',email],{env:process.env});
  await page.goto('/login'); await page.getByLabel(/e-mail|email/i).fill(email);
  await page.getByLabel(/senha|password/i).fill(process.env.E2E_PASSWORD??'synthetic-e2e-password-63');
  await page.getByRole('button',{name:/entrar|sign in/i}).click(); await expect(page).toHaveURL(/\/profile/);
}
function response(page:Page,path:string){return page.waitForResponse(value=>new URL(value.url()).origin===apiOrigin&&new URL(value.url()).pathname===path&&value.status()===200);}

test('real PostgreSQL: 4/null/0 reconciles current card, list, exact detail and older period',async({page})=>{
  await login(page); const pending=response(page,'/indicators');
  await page.goto(dashboard({organization_id:orgA})); const result=await pending;
  const body=await result.json(); expect(body.workorders.total).toBe(4);
  expect(body.workorders_current.total).toBe(3);
  expect(body.quantities_coverage.planned).toMatchObject({known_sum:4,known_count:2,total_count:3,state:'partial'});
  await expect(page.locator('.indicator-value').nth(1)).toHaveText('3');
  await expect(page.locator('[data-quantity="planned"]')).toContainText('Dados de 2 de 3 Workorders');
  await expect(page.locator('[data-quantity="planned"] .known-quantity')).toHaveText('4');
  await expect(page.locator('[data-quantity="produced"] .known-quantity')).toHaveText('0');
  await expect(page.locator('[data-quantity="received"]')).toContainText('Não informado');
  const listed=response(page,'/indicators/workorders'); await page.getByRole('link',{name:'Ver Workorders',exact:true}).click();
  const current=await(await listed).json(); expect(current.pagination.total).toBe(3);
  await expect(page.locator('.workorder-row')).toHaveCount(3);
  await page.locator('.workorder-row').filter({hasText:'WO-001'}).click();
  await expect(page.locator('.metadata')).toContainText('e2e196-a-1');
  expect(new URL(page.url()).searchParams.get('organization_id')).toBe(orgA);
  await expect(page.locator('.metrics strong').nth(0)).toHaveText('4');
  await page.getByRole('button',{name:'Voltar aos Workorders'}).click();
  await page.reload(); await expect(page.locator('.workorder-row')).toHaveCount(3);
  const auth={authorization:result.request().headers()['authorization']};
  const outside=await page.request.get(apiOrigin+'/indicators?organization_id='+orgB,{headers:auth});
  expect(outside.status()).toBe(403);
  const history=response(page,'/indicators');
  await page.goto('/dashboard?'+new URLSearchParams({organization_id:orgA,date_to:'2026-10-01T23:59:59Z'}));
  expect((await(await history).json()).workorders_current.total).toBe(1);
  await expect(page.locator('[data-quantity="planned"] .known-quantity')).toHaveText('400');
  await page.getByRole('link',{name:'Ver Workorders',exact:true}).click();
  await expect(page.locator('.workorder-row')).toHaveCount(1);
  await page.locator('.workorder-row').click(); await expect(page.locator('.metadata')).toContainText('e2e196-a-old');
});

test('real PostgreSQL: A/B aggregate and narrower detail permissions stay explicit',async({page})=>{
  await login(page,'both'); await page.goto(dashboard());
  await expect(page.locator('.indicator-value').nth(1)).toHaveText('4');
  await expect(page.locator('[data-quantity="planned"] .known-quantity')).toHaveText('1.003');
  await page.getByRole('link',{name:'Ver Workorders',exact:true}).click();
  await expect(page.locator('.workorder-row')).toHaveCount(4);
  await expect(page.locator('.workorder-list')).toContainText('Synthetic 196 B');
  await page.getByRole('button',{name:'Sair',exact:true}).click();
  await expect(page).toHaveURL(/\/login/);
  await login(page,'restricted'); await page.goto(dashboard());
  await expect(page.locator('.indicator-value').nth(1)).toHaveText('4');
  await expect(page.locator('.detail-scope-note')).toContainText('escopo de acesso mais restrito');
  await page.getByRole('link',{name:'Ver Workorders autorizadas'}).click();
  await expect(page.locator('.workorder-row')).toHaveCount(3);
  await expect(page.locator('.workorder-list')).not.toContainText('Synthetic 196 B');
  await expect(page.locator('.scope-note')).toContainText('Organizações no escopo dos detalhes: 1');
});

test('real PostgreSQL: empty period and dashboard-only permission do not invent quantity or detail access',async({page})=>{
  await login(page,'denied'); const pending=response(page,'/indicators'); await page.goto(dashboard({organization_id:orgA}));
  const result=await pending;
  await expect(page.locator('.indicator-value').nth(1)).toHaveText('3');
  await expect(page.locator('a[href*="/dashboard/related/workorders"]')).toHaveCount(0);
  const denied=await page.request.get(apiOrigin+'/indicators/workorders?view=current',{headers:{authorization:result.request().headers()['authorization']}});
  expect(denied.status()).toBe(403);
  await page.goto('/dashboard?date_from=2030-01-01T00%3A00%3A00Z');
  await expect(page.locator('.quantities-chart')).toContainText('Sem Workorders no período');
  await expect(page.locator('.quantities-chart .known-quantity')).toHaveCount(0);
  await expect(page.locator('.quantities-chart [role="meter"]')).toHaveCount(0);
});

test('real PostgreSQL: appended version replaces 4 by 7 without increasing denominator',async({page})=>{
  execFileSync(python,['../scripts/bootstrap_indicator_coverage_e2e.py','--append-version'],{env:{...process.env,SYNERGIA_ENV:'test'}});
  await login(page); const pending=response(page,'/indicators'); await page.goto(dashboard({organization_id:orgA}));
  const body=await(await pending).json(); expect(body.workorders.total).toBe(5);
  expect(body.workorders_current.total).toBe(3);
  expect(body.quantities_coverage.planned).toMatchObject({known_sum:7,known_count:2,total_count:3});
  await expect(page.locator('[data-quantity="planned"] .known-quantity')).toHaveText('7');
  await page.getByRole('link',{name:'Ver Workorders',exact:true}).click();
  await expect(page.locator('.workorder-row')).toHaveCount(3);
  await page.locator('.workorder-row').filter({hasText:'WO-001'}).click();
  await expect(page.locator('.metadata')).toContainText('e2e196-a-new');
  await expect(page.locator('.metrics strong').nth(0)).toHaveText('7');
});
