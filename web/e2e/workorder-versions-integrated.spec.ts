import { expect, Page, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';

const apiOrigin = `http://127.0.0.1:${process.env.E2E_API_PORT ?? '8000'}`;
const orgA = '19500000-0000-4000-8000-000000000001';
const orgB = '19500000-0000-4000-8000-000000000002';
const period = { started_from: '2026-10-01T04:00:00Z', started_to: '2026-10-06T03:59:59.999999Z' };
const search = (number: string, extra: Record<string, string> = {}) => '/search?' + new URLSearchParams({ type: 'workorder', query: number, pageSize: '10', sort: 'updated_desc', ...period, ...extra });

test.beforeAll(() => {
  execFileSync(process.env.E2E_PYTHON ?? 'python', ['../scripts/bootstrap_workorder_versions_e2e.py'], { env: { ...process.env, SYNERGIA_ENV: 'test' } });
});

async function login(page: Page, label = 'reader'): Promise<void> {
  const email = `workorders-${label}.e2e@example.invalid`;
  execFileSync(process.env.E2E_PYTHON ?? 'python', ['../scripts/bootstrap_web_e2e.py', '--revoke-email', email], { env: process.env });
  await page.goto('/login');
  await page.getByLabel(/e-mail|email/i).fill(email);
  await page.getByLabel(/senha|password/i).fill(process.env.E2E_PASSWORD ?? 'synthetic-e2e-password-63');
  await page.getByRole('button', { name: /entrar|sign in/i }).click();
  await expect(page).toHaveURL(/\/profile/);
}

function response(page: Page, pathname: string) {
  return page.waitForResponse(result => new URL(result.url()).origin === apiOrigin && new URL(result.url()).pathname === pathname && result.status() === 200);
}

test('real PostgreSQL: three A versions, current partial, history, exact old detail and return', async ({ page }) => {
  await login(page);
  const pending = response(page, '/search');
  await page.goto(search('000123', { organization_id: orgA }));
  const result = await pending; const current = await result.json();
  expect(new URL(result.url()).searchParams.get('view')).toBe('current');
  expect(current.pagination.total).toBe(1);
  expect(current.items[0].execution_id).toBe('e2e195-a-tie-later');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await expect(page.locator('tbody')).not.toContainText('Synthetic 195 B');
  const token = result.request().headers()['authorization'];
  const selected = await page.request.get(apiOrigin + '/workorders/000123/consolidated-result?organization_id=' + orgA, { headers: { authorization: token } });
  expect((await selected.json()).workorder).toMatchObject({ planned_quantity: null, produced_quantity: 0, snapshot_id: current.items[0].snapshot_id });
  const historyResponse = response(page, '/search');
  await page.getByRole('link', { name: 'Ver histórico', exact: true }).click();
  expect((await (await historyResponse).json()).pagination.total).toBe(3);
  await expect(page.locator('tbody tr')).toHaveCount(3);
  const from = new URL(page.url());
  const oldRow = page.locator('tbody tr').filter({ hasText: 'e2e195-a-old' });
  await oldRow.getByRole('link', { name: '000123', exact: true }).click();
  await expect(page.locator('.metadata')).toContainText('e2e195-a-old');
  await expect(page.locator('.metrics strong').nth(0)).toHaveText('40');
  await expect(page.locator('.metrics strong').nth(1)).toHaveText('20');
  expect(new URL(page.url()).searchParams.get('execution_id')).toBe('e2e195-a-old');
  await page.getByRole('button', { name: 'Voltar aos Workorders' }).click();
  expect(new URL(page.url()).pathname + new URL(page.url()).search).toBe(from.pathname + from.search);
  await expect(page.locator('tbody tr')).toHaveCount(3);
  await page.reload();
  await expect(page.getByLabel('Versões', { exact: true })).toHaveValue('history');
  expect(new URL(page.url()).searchParams.get('started_to')).toBe(period.started_to);
  const headers = { authorization: token };
  for (const endpoint of [
    `/workorders/000123?organization_id=${orgB}`,
    `/workorders/000123?execution_id=e2e195-b-current`,
    `/workorders/000123?execution_id=e2e195-a-unpublished`,
    `/workorders/000123?execution_id=e2e195-unknown-iam`
  ]) expect((await page.request.get(apiOrigin + endpoint, { headers })).status()).toBe(404);
  const outside = await page.request.get(apiOrigin + `/search?type=workorder&query=000123&view=current&organization_id=${orgB}`, { headers });
  expect((await outside.json()).pagination.total).toBe(0);
  expect((await page.request.get(apiOrigin + '/search?type=workorder&query=000123')).status()).toBe(401);
});

test('real PostgreSQL: same number in A/B stays separate and ambiguous detail does not pick a tenant', async ({ page }) => {
  await login(page, 'both');
  await page.goto(search('000123'));
  await expect(page.locator('tbody tr')).toHaveCount(2);
  await expect(page.locator('tbody')).toContainText('Synthetic 195 A');
  await expect(page.locator('tbody')).toContainText('Synthetic 195 B');
  await page.goto('/workorders/000123');
  await expect(page.getByText('Selecione a organização', { exact: true })).toBeVisible();
  await expect(page.locator('.metrics')).toHaveCount(0);
  await page.goto(search('000123'));
  await page.locator('tbody tr').filter({ hasText: 'Synthetic 195 B' }).getByRole('link', { name: '000123', exact: true }).click();
  await expect(page.locator('.metadata')).toContainText('e2e195-b-current');
  expect(new URL(page.url()).searchParams.get('organization_id')).toBe(orgB);
});

test('real PostgreSQL: history pagination, detail and reload preserve the applied period and page', async ({ page }) => {
  await login(page);
  await page.goto(search('000456', { organization_id: orgA }));
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByRole('link', { name: 'Ver histórico', exact: true }).click();
  await expect(page.locator('tbody tr')).toHaveCount(10);
  await page.getByRole('button', { name: 'Próxima', exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get('page')).toBe('2');
  await expect(page.locator('tbody tr').first()).toContainText('e2e195-paged-12');
  const from = page.url();
  await page.locator('tbody tr').first().getByRole('link', { name: '000456', exact: true }).click();
  await expect(page.locator('.metadata')).toContainText('e2e195-paged-12');
  await page.getByRole('button', { name: 'Voltar aos Workorders' }).click();
  await expect(page).toHaveURL(from);
  await page.reload();
  await expect(page.locator('tbody tr').first()).toContainText('e2e195-paged-12');
  expect(new URL(page.url()).searchParams.get('started_to')).toBe(period.started_to);
});

test('real PostgreSQL: period applies to execution start before choosing the current snapshot', async ({ page }) => {
  await login(page);
  await page.goto(search('000123', { organization_id: orgA, started_to: '2026-10-02T23:59:59.999999Z' }));
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await expect(page.locator('tbody')).toContainText('e2e195-a-tie-earlier');
  await page.locator('tbody tr').getByRole('link', { name: '000123', exact: true }).click();
  await expect(page.locator('.metadata')).toContainText('e2e195-a-tie-earlier');
  await expect(page.locator('.metrics strong').nth(1)).toHaveText('20');
});

test('real PostgreSQL: an authenticated actor without business.read receives 403', async ({ page }) => {
  const issued = response(page, '/auth/login');
  await login(page, 'denied');
  const access = (await (await issued).json()).access_token;
  const result = await page.request.get(apiOrigin + '/search?type=workorder&query=000123&view=current', { headers: { authorization: `Bearer ${access}` } });
  expect(result.status()).toBe(403);
});
