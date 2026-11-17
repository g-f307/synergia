import AxeBuilder from '@axe-core/playwright';
import { expect, Page, test, TestInfo } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

const email = 'reconciliation.e2e@example.invalid';
const organization = '19300000-0000-4000-8000-000000000001';
const cut = new URLSearchParams({
  source: 'OWM', file_type: 'csv',
  date_from: '2026-11-01T04:00:00Z', date_to: '2026-11-02T03:59:59.999999Z',
});

test.beforeAll(() => {
  execFileSync(process.env.E2E_PYTHON ?? 'python', ['../scripts/bootstrap_execution_reconciliation_e2e.py'], { env: process.env });
});

async function login(page: Page): Promise<void> {
  execFileSync(process.env.E2E_PYTHON ?? 'python', ['../scripts/bootstrap_web_e2e.py', '--revoke-email', email], { env: process.env });
  // Deliberately differ from the profile timezone: calendar inputs must use Manaus.
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/login');
  await page.getByLabel(/e-mail|email/i).fill(email);
  await page.getByLabel(/senha|password/i).fill(process.env.E2E_PASSWORD ?? 'synthetic-e2e-password-63');
  await page.getByRole('button', { name: /entrar|sign in/i }).click();
  await expect(page).toHaveURL(/\/profile/);
}

function api(page: Page, pathname: string): Promise<import('@playwright/test').Response> {
  return page.waitForResponse(response => new URL(response.url()).pathname === pathname && response.status() === 200);
}

async function assertCut(page: Page): Promise<void> {
  await expect.poll(() => new URL(page.url()).searchParams.get('date_to')).toBe(cut.get('date_to'));
  for (const [key, value] of cut) expect(new URL(page.url()).searchParams.get(key)).toBe(value);
}

async function assertCategories(page: Page, prefix: string): Promise<void> {
  await expect(page.locator(`${prefix}[data-outcome="completed"]`).locator('dd, strong').last()).toHaveText('3');
  await expect(page.locator(`${prefix}[data-outcome="partial"]`).locator('dd, strong').last()).toHaveText('2');
  await expect(page.locator(`${prefix}[data-outcome="skipped_duplicate"]`).locator('dd, strong').last()).toHaveText('9');
}

async function evidence(page: Page, info: TestInfo, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  const audit = await new AxeBuilder({ page }).analyze();
  await info.attach(`axe-${name}`, { body: Buffer.from(JSON.stringify(audit.violations)), contentType: 'application/json' });
  expect(audit.violations).toEqual([]);
  const overflow = await page.evaluate(() => ({
    viewport: innerWidth, width: document.documentElement.scrollWidth,
    elements: [...document.querySelectorAll('*')].filter(element => element.getBoundingClientRect().right > innerWidth + 1).slice(0, 12).map(element => ({ tag: element.tagName, class: element.className, right: element.getBoundingClientRect().right })),
  }));
  expect(overflow.width, JSON.stringify(overflow)).toBeLessThanOrEqual(overflow.viewport);
  await info.attach(name, { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
}

test('reconciles 3/2/9 across the real dashboard, catalog, detail and TV, preserving the profile day', async ({ page }, info) => {
  await login(page);
  await page.goto('/dashboard');
  await expect(page.locator('.indicator-value').first()).toHaveText('30');
  await page.locator('.dashboard-filters summary').click();
  await page.getByLabel('Período inicial').fill('2026-11-01');
  await page.getByLabel('Período final').fill('2026-11-01');
  await page.getByLabel('Origem', { exact: true }).fill('OWM');
  await page.getByLabel('Tipo de arquivo', { exact: true }).fill('csv');
  const dashboardResponse = api(page, '/indicators');
  await page.getByRole('button', { name: 'Aplicar', exact: true }).click();
  const dashboard = (await (await dashboardResponse).json()).execution_summary;
  expect(dashboard.total).toBe(14);
  expect(dashboard.scope).toEqual({ permission: 'dashboard.read', organization_ids: [organization] });
  expect(dashboard.filters.date_to).toBe(cut.get('date_to'));
  await expect(page.locator('.indicator-value').first()).toHaveText('14');
  await expect(page.locator('.indicator-detail').first()).toHaveText('Concluídas: 3');
  await expect(page.locator('.status-legend')).toContainText('Ignoradas por duplicidade9');
  await assertCut(page);
  const summaryResponse = api(page, '/executions/summary');
  await page.getByRole('link', { name: 'Consultar execução', exact: true }).click();
  const summary = await (await summaryResponse).json();
  expect(summary.by_outcome).toEqual(dashboard.by_outcome);
  expect(summary.filters).toEqual(dashboard.filters);
  expect(summary.scope).toEqual({ permission: 'execution.read', organization_ids: [organization] });
  await assertCut(page);
  await assertCategories(page, '.outcome-totals div');
  await expect(page.locator('.execution-row')).toHaveCount(14);
  await expect(page.locator('.execution-row').filter({ hasText: 'e2e193-b-' })).toHaveCount(0);
  await page.locator('.execution-row').filter({ hasText: 'e2e193-a-13' }).click();
  await expect(page.locator('.lifecycle-badge')).toHaveText('Ignoradas por duplicidade');
  await expect(page.locator('.persisted-state')).toHaveAttribute('title', 'duplicate');
  await page.getByRole('button', { name: /voltar ao monitor/i }).click();
  await assertCut(page);
  await page.getByRole('link', { name: /abrir modo tv/i }).click();
  await assertCut(page);
  await assertCategories(page, '.tv-kpi');
  await expect(page.locator('.tv-kpi strong').first()).toHaveText('14');
  await expect(page.locator('.tv-recent-cut')).toHaveText('Exibindo 6 de 14 execuções do recorte.');
  await page.getByRole('button', { name: 'Atividade por fonte', exact: true }).click();
  await expect(page.locator('.tv-source-card header strong')).toContainText('14');
  await expect(page.locator('.tv-source-card header small')).toHaveText('Execuções desta fonte no período exibido');
  await expect(page.locator('.tv-source-card dd').first()).toHaveText('140');
  await evidence(page, info, 'reconciliation-sources');
  await page.getByRole('button', { name: 'Sair do Modo TV', exact: true }).click();
  await assertCut(page);
  await expect(page.locator('.indicator-value').first()).toHaveText('14');
});

test('keeps complete totals beyond page 25 and filters by outcome without reinterpreting legacy links', async ({ page }) => {
  await login(page);
  await page.goto('/executions');
  await expect(page.locator('.results-heading')).toContainText('30 resultado(s)');
  await expect(page.locator('.execution-row')).toHaveCount(20);
  await page.getByRole('link', { name: /abrir modo tv/i }).click();
  await expect(page.locator('.tv-kpi strong').first()).toHaveText('30');
  await expect(page.locator('.tv-kpi[data-outcome="completed"] strong')).toHaveText('7');
  await expect(page.locator('.tv-execution-table tbody tr')).toHaveCount(6);
  await page.getByRole('button', { name: 'Atividade por fonte', exact: true }).click();
  await expect(page.locator('.tv-source-card')).toHaveCount(3);
  await expect(page.locator('.tv-source-card')).toContainText(['N-FP', 'OWM', 'Fonte não informada']);
  await page.goto(`/executions?${cut}&outcome=skipped_duplicate`);
  await expect(page.locator('.results-heading')).toContainText('9 resultado(s)');
  await page.getByRole('link', { name: /abrir modo tv/i }).click();
  await expect(page.locator('.tv-kpi[data-outcome="skipped_duplicate"] strong')).toHaveText('9');
  await expect(page.locator('.tv-kpi[data-outcome="completed"] strong')).toHaveText('0');
  await page.goto(`/dashboard?${cut}&lifecycle=completed`);
  await expect(page.locator('.indicator-value').first()).toHaveText('12');
  await page.locator('.dashboard-filters summary').click();
  const legacyDashboardResponse = api(page, '/indicators');
  await page.getByRole('button', { name: 'Aplicar', exact: true }).click();
  expect((await (await legacyDashboardResponse).json()).execution_summary.filters.lifecycle).toBe('completed');
  await expect(page.locator('.indicator-value').first()).toHaveText('12');
  await page.goto(`/executions?${cut}&lifecycle=completed`);
  await expect(page.locator('.results-heading')).toContainText('12 resultado(s)');
  await page.locator('.catalog-filters summary').click();
  const legacyCatalogResponse = api(page, '/executions/summary');
  await page.getByRole('button', { name: 'Aplicar filtros', exact: true }).click();
  expect((await (await legacyCatalogResponse).json()).filters.lifecycle).toBe('completed');
  await expect(page.locator('.results-heading')).toContainText('12 resultado(s)');
  await page.locator('#execution-outcome').selectOption('partial');
  await page.getByRole('button', { name: 'Aplicar filtros', exact: true }).click();
  await expect(page.locator('.results-heading')).toContainText('2 resultado(s)');
  await expect.poll(() => new URL(page.url()).searchParams.has('lifecycle')).toBe(false);
});

test('keeps a complete stale frame on refresh failure and clears it on authorization loss', async ({ page }) => {
  await login(page);
  await page.goto(`/executions?${cut}`);
  await expect(page.locator('.results-heading')).toContainText('14 resultado(s)');
  await page.route(/\/executions\/summary(?:\?|$)/, route => route.fulfill({ status: 503, json: { error: { code: 'synthetic_unavailable', message: 'Unavailable', details: {} } } }));
  await page.locator('.catalog-filters summary').click();
  await page.locator('#execution-outcome').selectOption('completed');
  await page.getByRole('button', { name: 'Aplicar filtros', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('últimos dados obtidos e seu recorte');
  await assertCategories(page, '.outcome-totals div');
  await expect(page.locator('.execution-row')).toHaveCount(14);
  await assertCut(page);
  expect(new URL(page.url()).searchParams.has('outcome')).toBe(false);
  await page.unroute(/\/executions\/summary(?:\?|$)/);
  await page.route(/\/executions\/summary(?:\?|$)/, route => route.fulfill({ status: 403, json: { error: { code: 'access_denied', message: 'Denied', details: {} } } }));
  await page.getByRole('button', { name: 'Aplicar filtros', exact: true }).click();
  await expect(page.locator('.execution-row')).toHaveCount(0);
  await expect(page.locator('.outcome-totals')).toHaveCount(0);
  await expect(page.getByRole('status')).toContainText('Acesso proibido');
});

for (const width of [390, 768, 1440]) {
  for (const theme of ['light', 'dark']) {
    test(`visual, keyboard and accessibility: ${width}px ${theme}`, async ({ page }, info) => {
      test.setTimeout(90_000);
      await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
      await login(page);
      for (const route of ['dashboard', 'executions', 'tv']) {
        await page.goto(`/${route}?${cut}`);
        await expect(page.locator('.execution-scope')).toBeVisible();
        if (await page.locator('html').getAttribute('data-theme') !== theme) {
          await page.getByRole('button', { name: /alternar tema|toggle theme/i }).click();
        }
        const disclosure = page.locator('.execution-scope summary');
        await disclosure.focus();
        await page.keyboard.press('Enter');
        await expect(page.locator('.execution-scope')).toHaveAttribute('open', '');
        expect(await disclosure.evaluate(element => getComputedStyle(element).outlineStyle)).not.toBe('none');
        await page.keyboard.press('Enter');
        await evidence(page, info, `issue-193-${route}-${width}-${theme}`);
        if (route !== 'tv') {
          const metrics = await page.evaluate(() => ({
            documentScroll: document.documentElement.scrollHeight > innerHeight,
            frame: getComputedStyle(document.querySelector('.dashboard-surface, .execution-catalog')!).overflowY,
          }));
          expect(metrics.documentScroll).toBe(false);
          expect(metrics.frame).toBe('auto');
        } else {
          await page.getByRole('button', { name: 'Atividade por fonte', exact: true }).click();
          await evidence(page, info, `issue-193-sources-${width}-${theme}`);
        }
      }
    });
  }
}

test('native browser zoom 250% preserves readable, accessible and operable screens', async ({ playwright }, info) => {
  test.skip(process.env.E2E_NATIVE_ZOOM !== 'true', 'Opt-in: requires Chromium with unpacked extension support.');
  test.setTimeout(90_000);
  const profile = await mkdtemp(path.join(tmpdir(), 'synergia-193-zoom-'));
  const extension = path.resolve('e2e/support/native-zoom');
  const context = await playwright.chromium.launchPersistentContext(profile, {
    headless: true, viewport: { width: 1440, height: 1000 },
    executablePath: process.env.E2E_BROWSER_EXECUTABLE_PATH,
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
  });
  try {
    const page = context.pages()[0];
    await login(page);
    const worker = context.serviceWorkers()[0] ?? await context.waitForEvent('serviceworker');
    // Invoke the actual browser API, not CSS zoom, pinch zoom or viewport emulation.
    const zoom = await worker.evaluate(async () => {
      const extensionApi = (globalThis as unknown as { chrome: { tabs: {
        query(query: { active: boolean }): Promise<Array<{ id: number }>>;
        setZoom(tabId: number, factor: number): Promise<void>;
        getZoom(tabId: number): Promise<number>;
      } } }).chrome;
      const [tab] = await extensionApi.tabs.query({ active: true });
      await extensionApi.tabs.setZoom(tab.id, 2.5);
      return extensionApi.tabs.getZoom(tab.id);
    });
    expect(zoom).toBe(2.5);
    await expect.poll(() => page.evaluate(() => devicePixelRatio)).toBe(2.5);
    expect(await page.evaluate(() => innerWidth)).toBe(576);
    await info.attach('native-zoom-metrics', { body: Buffer.from(JSON.stringify({ zoom, ...await page.evaluate(() => ({ innerWidth, outerWidth, devicePixelRatio })) })), contentType: 'application/json' });
    for (const theme of ['light', 'dark']) {
      for (const route of ['dashboard', 'executions', 'tv']) {
        await page.goto(`/${route}?${cut}`);
        await expect(page.locator('.execution-scope')).toBeVisible();
        if (await page.locator('html').getAttribute('data-theme') !== theme) {
          await page.getByRole('button', { name: /alternar tema/i }).click();
        }
        await evidence(page, info, `issue-193-${route}-zoom250-${theme}`);
        if (route === 'executions') {
          await page.locator('.execution-row').last().click();
          await expect(page.locator('.lifecycle-badge')).toBeVisible();
          await page.getByRole('button', { name: /voltar ao monitor/i }).click();
        }
      }
    }
  } finally {
    await context.close();
    await rm(profile, { recursive: true, force: true });
  }
});
