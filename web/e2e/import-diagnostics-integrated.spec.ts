import AxeBuilder from '@axe-core/playwright';
import { expect, Page, test, TestInfo } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

const apiOrigin = `http://127.0.0.1:${process.env.E2E_API_PORT ?? '8000'}`;
const webOrigin = `http://127.0.0.1:${process.env.E2E_WEB_PORT ?? '4200'}`;
const python = process.env.E2E_PYTHON ?? 'python';
const storage = process.env.IMPORT_STORAGE_DIR ?? path.resolve('../.test-tmp/e2e-imports');

function fixture(action: string, ...args: string[]): string {
  return execFileSync(python, ['../scripts/bootstrap_import_diagnostics_e2e.py', action, ...args], { env: process.env, encoding: 'utf8' }).trim();
}
test.beforeAll(() => { fixture('seed'); });

async function login(page: Page, actor = 'imports-reader.e2e@example.invalid'): Promise<Record<string, string>> {
  execFileSync(python, ['../scripts/bootstrap_web_e2e.py', '--revoke-email', actor], { env: process.env });
  await page.context().clearCookies();
  await page.goto('/login');
  await page.getByLabel(/e-mail|email/i).fill(actor);
  await page.getByLabel(/senha|password/i).fill(process.env.E2E_PASSWORD ?? 'synthetic-e2e-password-63');
  const response = page.waitForResponse(res => res.url() === `${apiOrigin}/auth/login`);
  await page.getByRole('button', { name: /entrar|sign in/i }).click();
  const token = (await (await response).json()).access_token as string;
  await expect(page).toHaveURL(/\/profile/);
  return { Authorization: `Bearer ${token}` };
}

async function audit(page: Page, info: TestInfo, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  const result = await new AxeBuilder({ page }).analyze();
  await info.attach(`axe-${name}`, { body: JSON.stringify(result.violations), contentType: 'application/json' });
  expect(result.violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await page.locator('.detail-scroll').evaluate(el => { el.scrollTop = 0; });
  const file = info.outputPath(name + '.png');
  await page.screenshot({ path: file });
  await info.attach(name, { path: file, contentType: 'image/png' });
}

test('real persisted counts survive physical artifact removal; pages, CSV and history reconcile', async ({ page }, info) => {
  const headers = await login(page);
  fixture('remove-artifact', '--execution', 'ready');
  const before = JSON.parse(fixture('snapshot'));
  await page.goto('/imports/e2e194-ready');
  await expect(page.locator('tbody tr')).toHaveCount(20);
  expect(await page.locator('[data-testid="import-counts"] dd').allTextContents()).toEqual(['55', '35', '20', '35', '20', '35']);
  const summary = await (await page.request.get(`${apiOrigin}/imports/e2e194-ready/result-summary`, { headers })).json();
  expect(summary.issues_total).toBe(summary.summary.errors + summary.summary.warnings);
  expect((await page.request.get(`${apiOrigin}/imports/e2e194-ready/pipeline-summary`, { headers })).status()).toBe(404);
  await expect(page.locator('[data-testid="related-execution"]')).toHaveCount(0);
  await page.getByRole('button', { name: 'Próxima' }).click();
  await expect(page).toHaveURL(/page=2/);
  await page.getByRole('button', { name: 'Próxima' }).click();
  await expect(page.locator('tbody tr')).toHaveCount(15);
  await page.getByLabel('Severidade', { exact: true }).selectOption('warning');
  await expect(page.locator('tbody tr')).toHaveCount(20);
  await expect(page).toHaveURL(/severity=warning/);
  expect(new URL(page.url()).searchParams.get('page')).toBe('1');
  await page.getByRole('button', { name: 'Próxima' }).click();
  await expect(page.locator('tbody tr')).toHaveCount(15);
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Exportar CSV do filtro' }).click();
  const download = await downloaded; const stream = await download.createReadStream(); const chunks = [];
  for await (const chunk of stream!) chunks.push(chunk);
  const csv = Buffer.concat(chunks).toString('utf8');
  expect(download.suggestedFilename()).toBe('import-issues.csv');
  expect(csv.trim().split('\r\n')).toHaveLength(36);
  expect(csv).not.toContain('synthetic-sensitive-cell');
  expect(await page.locator('body').textContent()).not.toContain('synthetic-sensitive-cell');
  const after = JSON.parse(fixture('snapshot')); expect(after).toEqual(before);
  await info.attach('read-only-reconciliation', { body: JSON.stringify({ before, after, occurrences: 55, errors: 20, warnings: 35, csv_filtered: 35 }), contentType: 'application/json' });
});

test('real terminal state without artifact or persisted summary never becomes pending', async ({ page }, info) => {
  await login(page);
  fixture('remove-artifact', '--execution', 'missing', '--persisted');
  const before = JSON.parse(fixture('snapshot'));
  await page.goto('/imports/e2e194-missing');
  await expect(page.locator('.summary-section')).toContainText('Não há contagens persistidas');
  await expect(page.locator('.summary-section')).not.toContainText('processamento está em andamento');
  await expect(page.locator('[data-testid="import-counts"]')).toHaveCount(0);
  await page.locator('.summary-section').getByText('Detalhes técnicos', { exact: true }).click();
  await expect(page.getByLabel('ID de correlação', { exact: true })).toHaveValue(/^[a-f0-9-]{36}$/i);
  await page.locator('.summary-section').getByRole('button', { name: 'Atualizar resultado' }).click();
  await expect(page.locator('.summary-section')).toContainText('Não há contagens persistidas');
  expect(JSON.parse(fixture('snapshot'))).toEqual(before);
  await audit(page, info, 'issue-194-missing-persisted-summary');
});

test('real preparation, rejection, duplicate, zero, success and active states remain distinct', async ({ page }) => {
  await login(page);
  for (const [label, text] of [
    ['preparation', 'falhou na preparação'], ['rejected', 'Macros ou conteúdo ativo'],
    ['duplicate', 'Nenhum processamento duplicado'], ['active', 'processamento está em andamento'],
  ]) {
    await page.goto('/imports/e2e194-' + label);
    await expect(page.locator('.summary-section')).toContainText(text);
    await expect(page.locator('[data-testid="import-counts"]')).toHaveCount(0);
  }
  await page.goto('/imports/e2e194-duplicate');
  await expect(page.getByRole('link', { name: 'Ver importação anterior' })).toHaveAttribute('href', '/imports/e2e194-ready');
  await page.goto('/imports/e2e194-duplicate-b');
  await expect(page.locator('.summary-section')).toContainText('Nenhum processamento duplicado');
  await expect(page.getByRole('link', { name: 'Ver importação anterior' })).toHaveCount(0);
  for (const label of ['zero', 'success']) {
    await page.goto('/imports/e2e194-' + label);
    await expect(page.locator('[data-testid="import-counts"] dd')).toHaveCount(6);
    await expect(page.locator('.issues-section')).toContainText('Nenhuma divergência registrada');
    await expect(page.locator('syn-pagination')).toHaveCount(0);
  }
});

test('real IAM permits import.read only, denies other organization and preserves 401/403/404', async ({ page }) => {
  const headers = await login(page);
  for (const suffix of ['result-summary', 'issues', 'issues/export']) {
    expect((await page.request.get(`${apiOrigin}/imports/e2e194-ready/${suffix}`, { headers })).status()).toBe(200);
    expect((await page.request.get(`${apiOrigin}/imports/e2e194-outside/${suffix}`, { headers })).status()).toBe(404);
    expect((await page.request.get(`${apiOrigin}/imports/e2e194-ready/${suffix}`)).status()).toBe(401);
  }
  expect((await page.request.get(`${apiOrigin}/executions/e2e194-ready/divergences`, { headers })).status()).toBe(403);
  await page.goto('/imports/e2e194-outside');
  await expect(page.locator('.detail-scroll syn-state')).toContainText('Importação indisponível');
  await expect(page.locator('.detail-scroll')).not.toContainText('processamento está em andamento');
  const unrelated = await login(page, 'reader.e2e@example.invalid');
  expect((await page.request.get(`${apiOrigin}/imports/e2e194-ready/issues`, { headers: unrelated })).status()).toBe(403);
});

test('controlled 503 on the real issues request preserves persisted results and recovers', async ({ page }) => {
  await login(page);
  const url = `${apiOrigin}/imports/e2e194-ready/issues*`;
  await page.route(url, async route => {
    const response = await route.fetch(); expect(response.status()).toBe(200);
    await route.fulfill({ response, status: 503, json: { error: { code: 'import_issues_unavailable', message: 'synthetic error' } } });
  });
  await page.goto('/imports/e2e194-ready');
  await expect(page.locator('.issues-section')).toContainText('temporariamente indisponível');
  await expect(page.locator('[data-testid="import-counts"] dd')).toHaveCount(6);
  await page.unroute(url);
  await page.locator('.issues-section').getByRole('button', { name: 'Tentar consulta novamente' }).click();
  await expect(page.locator('tbody tr')).toHaveCount(20);
  await expect(page.locator('[data-testid="import-counts"] dd')).toHaveCount(6);
});

test('real CSV upload exposes row/field errors and macro upload stays rejected', async ({ page }) => {
  await login(page, 'imports-creator.e2e@example.invalid');
  await page.goto('/imports/new');
  await page.locator('#import-file').setInputFiles({ name: 'synthetic-errors.csv', mimeType: 'text/csv', buffer: Buffer.from(`workorder,status,planned_quantity\n,open,-1\nWO-SYN194-${Date.now()},open,1\n`) });
  await page.getByRole('button', { name: 'Enviar arquivo', exact: true }).click();
  await expect(page).toHaveURL(/\/imports\/[a-f0-9-]{36}$/, { timeout: 30_000 });
  await expect(page.locator('tbody')).toContainText('required_field');
  await expect(page.locator('tbody')).toContainText('invalid_quantity');
  await expect(page.locator('.status-pill')).toHaveText('Concluída com erros');
  expect(await page.locator('[data-testid="import-counts"] dd').allTextContents()).toEqual(['2', '1', '1', '1', '2', '0']);
  await page.goto('/imports/new');
  await page.locator('#import-file').setInputFiles(path.join(storage, 'synthetic-macro.xlsx'));
  await page.getByRole('button', { name: 'Enviar arquivo', exact: true }).click();
  await page.getByRole('link', { name: 'Ver resultado da importação' }).click();
  await expect(page.locator('.summary-section')).toContainText('Macros ou conteúdo ativo');
  await expect(page.locator('[data-testid="import-counts"]')).toHaveCount(0);
});

for (const width of [390, 768, 1440]) {
  for (const theme of ['light', 'dark']) {
    test(`real persisted diagnostics ${width}px ${theme}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 960 });
      await login(page); await page.goto('/imports/e2e194-ready');
      await expect(page.locator('tbody tr')).toHaveCount(20);
      if (theme === 'dark') await page.locator('.theme-button').click();
      await page.getByLabel('Severidade', { exact: true }).focus(); await page.keyboard.press('Tab');
      await expect(page.getByRole('button', { name: 'Exportar CSV do filtro' })).toBeFocused();
      expect(await page.locator('.detail-scroll').evaluate(el => getComputedStyle(el).overflowY)).toBe('auto');
      await audit(page, info, `issue-194-real-${width}-${theme}`);
    });
  }
}

test('real diagnostics at native browser zoom 250% in both themes', async ({ playwright }, info) => {
  test.skip(process.env.E2E_NATIVE_ZOOM !== 'true', 'Opt-in native extension check.');
  test.setTimeout(90_000);
  const profile = await mkdtemp(path.join(tmpdir(), 'synergia-194-zoom-'));
  const extension = path.resolve('e2e/support/native-zoom');
  const context = await playwright.chromium.launchPersistentContext(profile, {
    headless: true, viewport: { width: 1440, height: 1000 }, executablePath: process.env.E2E_BROWSER_EXECUTABLE_PATH,
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
  });
  try {
    const page = context.pages()[0]; await login(page);
    const worker = context.serviceWorkers()[0] ?? await context.waitForEvent('serviceworker');
    const zoom = await worker.evaluate(async () => {
      const api = (globalThis as unknown as { chrome: { tabs: {
        query(query: { active: boolean }): Promise<Array<{ id: number }>>;
        setZoom(id: number, factor: number): Promise<void>; getZoom(id: number): Promise<number>;
      } } }).chrome;
      const [tab] = await api.tabs.query({ active: true }); await api.tabs.setZoom(tab.id, 2.5);
      return api.tabs.getZoom(tab.id);
    });
    expect(zoom).toBe(2.5);
    await page.goto(webOrigin + '/imports/e2e194-ready');
    await expect.poll(() => page.evaluate(() => devicePixelRatio)).toBe(2.5);
    expect(await page.evaluate(() => innerWidth)).toBe(576);
    for (const theme of ['light', 'dark']) {
      if (await page.locator('html').getAttribute('data-theme') !== theme) await page.locator('.theme-button').click();
      await expect(page.locator('tbody tr')).toHaveCount(20);
      await page.getByLabel('Severidade', { exact: true }).selectOption('warning');
      await expect(page).toHaveURL(/severity=warning/);
      await audit(page, info, `issue-194-real-zoom250-${theme}`);
    }
    await info.attach('native-zoom', { body: JSON.stringify({ factor: zoom, ...await page.evaluate(() => ({ innerWidth, devicePixelRatio })) }), contentType: 'application/json' });
  } finally { await context.close(); await rm(profile, { recursive: true, force: true }); }
});
