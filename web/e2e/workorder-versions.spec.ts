import AxeBuilder from '@axe-core/playwright';
import { expect, Page, test, TestInfo } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

const apiOrigin = `http://127.0.0.1:${process.env.E2E_API_PORT ?? '8000'}`;
const webOrigin = `http://127.0.0.1:${process.env.E2E_WEB_PORT ?? '4200'}`;
const organization = '19500000-0000-4000-8000-000000000001';
const period = { started_from: '2026-10-01T04:00:00Z', started_to: '2026-10-06T03:59:59.999999Z' };
const searchUrl = '/search?' + new URLSearchParams({ type: 'workorder', query: '000123', organization_id: organization, ...period, pageSize: '10', sort: 'updated_desc' });

// Synthetic HTTP contracts test browser behavior. PostgreSQL selection and real
// authorization are covered independently by the #195 persistence tests.
async function contracts(page: Page, locale = 'pt-BR'): Promise<void> {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route(`${apiOrigin}/**`, async route => {
    const request = route.request(); const url = new URL(request.url());
    const headers = { 'access-control-allow-origin': webOrigin, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'authorization,content-type', 'x-correlation-id': 'synthetic-195' };
    const json = (body: unknown, status = 200) => route.fulfill({ status, headers, contentType: 'application/json', body: JSON.stringify(body) });
    if (request.method() === 'OPTIONS') { await route.fulfill({ status: 204, headers }); return; }
    if (url.pathname === '/auth/refresh') { await json({ access_token: 'synthetic-token', token_type: 'Bearer', expires_in: 3600, session_id: 'synthetic-session' }); return; }
    if (url.pathname === '/me') { await json({ id: 'synthetic-user', status: 'active', display_name: 'Operador sintético', emails: [], locale, timezone: 'America/Manaus', notifications: { email: false, in_app: false }, appearance: { density: 'comfortable', font_scale: 'normal' }, avatar: null, permissions: [{ key: 'business.read', organizations: [organization] }], version: 1 }); return; }
    if (url.pathname === '/notifications/unread-count') { await json({ count: 0 }); return; }
    if (url.pathname === '/search') {
      expect(url.searchParams.get('organization_id')).toBe(organization);
      expect(url.searchParams.get('started_to')).toBe(period.started_to);
      expect(url.searchParams.get('view')).toMatch(/^(current|history)$/);
      const history = url.searchParams.get('view') === 'history';
      const count = history ? 23 : 1;
      const currentPage = Number(url.searchParams.get('page') ?? 1);
      const size = Number(url.searchParams.get('page_size') ?? 10);
      const versions = Array.from({ length: count }, (_, index) => ({ entity_type: 'workorder', identifier: '000123', workorder_number: '000123', execution_id: `exec-${23 - index}`, organization_id: organization, organization_name: 'Synthetic A', organization_code: 'WORKBOOK-CODE', snapshot_id: 23 - index, processing_status: 'consolidated', lot_number: null, serial_number: null, updated_at: `2026-10-${String(5 - Math.floor(index / 6)).padStart(2, '0')}T12:00:00Z` }));
      await json({ items: versions.slice((currentPage - 1) * size, currentPage * size), view: history ? 'history' : 'current', entity_type: 'workorder', query: '000123', sort: 'updated_desc', pagination: { page: currentPage, page_size: size, total: count, pages: Math.ceil(count / size) }, source: 'synergia.operational', generated_at: new Date().toISOString() }); return;
    }
    if (url.pathname === '/workorders/000123/consolidated-result') {
      expect(url.searchParams.get('organization_id')).toBe(organization);
      const execution = url.searchParams.get('execution_id');
      await json({ workorder: { execution_id: execution, organization_id: organization, organization_name: 'Synthetic A', organization_code: 'WORKBOOK-CODE', snapshot_id: Number(execution?.split('-')[1]), workorder_number: '000123', processing_status: 'consolidated', planned_quantity: null, produced_quantity: 0, received_quantity: 9, released_quantity: 6, pending_quantity: null, retained_quantity: null, partially_released: null, lots: [], serials: [], updated_at: '2026-10-02T12:00:00Z' }, classifications: [], pending_items: [], provenance: [] }); return;
    }
    await json({ code: 'resource_not_found', message: 'Synthetic missing resource' }, 404);
  });
}

async function evidence(page: Page, info: TestInfo, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  const audit = await new AxeBuilder({ page }).analyze();
  await info.attach(`axe-${name}`, { body: JSON.stringify(audit.violations), contentType: 'application/json' });
  expect(audit.violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await info.attach(name, { body: await page.screenshot(), contentType: 'image/png' });
}

for (const width of [390, 768, 1440]) {
  for (const theme of ['light', 'dark']) {
    test(`current/history and pinned detail at ${width}px, ${theme} (synthetic HTTP)`, async ({ page }, info) => {
      await contracts(page);
      await page.setViewportSize({ width, height: 960 });
      await page.goto(searchUrl);
      await expect(page.locator('tbody tr')).toHaveCount(1);
      await expect(page.getByLabel('Versões', { exact: true })).toHaveValue('current');
      if (theme === 'dark') await page.locator('.theme-button').click();
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await page.getByLabel('Versões', { exact: true }).focus();
      await page.keyboard.press('Tab');
      await expect(page.getByRole('button', { name: 'Buscar', exact: true })).toBeFocused();
      await evidence(page, info, `current-${width}-${theme}`);
      await page.getByRole('link', { name: 'Ver histórico', exact: true }).click();
      await expect(page.locator('tbody tr')).toHaveCount(10);
      await expect(page.getByLabel('Versões', { exact: true })).toHaveValue('history');
      await page.getByRole('button', { name: 'Próxima', exact: true }).click();
      await expect.poll(() => new URL(page.url()).searchParams.get('page')).toBe('2');
      const from = new URL(page.url());
      expect(from.searchParams.get('organization_id')).toBe(organization);
      expect(from.searchParams.get('started_to')).toBe(period.started_to);
      const origin = from.pathname + from.search;
      await evidence(page, info, `history-${width}-${theme}`);
      await page.locator('tbody tr').first().getByRole('link', { name: '000123', exact: true }).click();
      await expect(page.locator('.metadata')).toContainText('exec-13');
      expect(new URL(page.url()).searchParams.get('execution_id')).toBe('exec-13');
      expect(new URL(page.url()).searchParams.get('organization_id')).toBe(organization);
      await evidence(page, info, `detail-${width}-${theme}`);
      await page.getByRole('button', { name: 'Voltar aos Workorders' }).click();
      await expect(page).toHaveURL(webOrigin + origin);
      await expect(page.locator('tbody tr')).toHaveCount(10);
      await page.reload();
      await expect(page.getByLabel('Versões', { exact: true })).toHaveValue('history');
      await expect(page.locator('tbody tr').first()).toContainText('exec-13');
    });
  }
}

test('English labels and empty history (synthetic HTTP)', async ({ page }) => {
  await contracts(page, 'en-US');
  await page.goto(searchUrl + '&view=history&page=4');
  await expect(page.getByLabel('Versions', { exact: true })).toHaveValue('history');
  await expect(page.getByRole('heading', { name: 'Workorder history in scope' })).toBeVisible();
  await expect(page.locator('tbody')).toHaveCount(0);
});

test('native zoom 250% keeps search, history and pinned detail usable in both themes', async ({ playwright }, info) => {
  test.skip(process.env.E2E_NATIVE_ZOOM !== 'true', 'Opt-in: Chromium extension support required.');
  test.setTimeout(90_000);
  const profile = await mkdtemp(path.join(tmpdir(), 'synergia-195-zoom-'));
  const extension = path.join(info.project.testDir, 'support/native-zoom');
  const context = await playwright.chromium.launchPersistentContext(profile, {
    headless: true, viewport: { width: 1440, height: 1000 },
    executablePath: process.env.E2E_BROWSER_EXECUTABLE_PATH,
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`]
  });
  try {
    const page = context.pages()[0];
    await contracts(page);
    await page.goto(webOrigin + searchUrl);
    await expect(page.locator('tbody tr')).toHaveCount(1);
    const worker = context.serviceWorkers()[0] ?? await context.waitForEvent('serviceworker');
    const zoom = await worker.evaluate(async () => {
      const api = (globalThis as unknown as { chrome: { tabs: {
        query(query: { active: boolean }): Promise<Array<{ id: number }>>;
        setZoom(id: number, factor: number): Promise<void>; getZoom(id: number): Promise<number>;
      } } }).chrome;
      const [tab] = await api.tabs.query({ active: true });
      await api.tabs.setZoom(tab.id, 2.5);
      return api.tabs.getZoom(tab.id);
    });
    expect(zoom).toBe(2.5);
    await expect.poll(() => page.evaluate(() => devicePixelRatio)).toBe(2.5);
    await info.attach('native-zoom', { body: JSON.stringify({ factor: zoom, ...await page.evaluate(() => ({ innerWidth, devicePixelRatio })) }), contentType: 'application/json' });
    for (const theme of ['light', 'dark']) {
      await page.goto(webOrigin + searchUrl);
      await expect(page.locator('tbody tr')).toHaveCount(1);
      if (await page.locator('html').getAttribute('data-theme') !== theme) await page.locator('.theme-button').click();
      await evidence(page, info, `current-zoom250-${theme}`);
      await page.getByRole('link', { name: 'Ver histórico', exact: true }).click();
      await expect(page.locator('tbody tr')).toHaveCount(10);
      await evidence(page, info, `history-zoom250-${theme}`);
      const table = page.locator('syn-responsive-table [tabindex="0"]');
      await table.focus(); await table.press('ArrowRight');
      await expect.poll(() => table.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
      await page.locator('tbody tr').first().getByRole('link', { name: '000123', exact: true }).click();
      await expect(page.locator('.metadata')).toContainText('exec-23');
      await evidence(page, info, `detail-zoom250-${theme}`);
      await page.getByRole('button', { name: 'Voltar aos Workorders' }).click();
      await expect(page.getByLabel('Versões', { exact: true })).toHaveValue('history');
    }
  } finally {
    await context.close();
    await rm(profile, { recursive: true, force: true });
  }
});
