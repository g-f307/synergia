import AxeBuilder from '@axe-core/playwright';
import { expect, Page, test } from '@playwright/test';

const apiOrigin = `http://127.0.0.1:${process.env.E2E_API_PORT ?? '8000'}`;
const webOrigin = `http://127.0.0.1:${process.env.E2E_WEB_PORT ?? '4200'}`;
const generated = '2026-11-17T12:00:00Z';
type Scenario = { failIssues: boolean; availability: 'ready' | 'unavailable'; locale: 'pt-BR' | 'en-US' };

async function contracts(page: Page, scenario: Scenario): Promise<void> {
  await page.route(`${apiOrigin}/**`, async route => {
    const request = route.request(); const url = new URL(request.url()); const pathname = url.pathname;
    const headers = { 'access-control-allow-origin': webOrigin, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'authorization,content-type', 'access-control-expose-headers': 'X-Correlation-ID,Content-Disposition', 'x-correlation-id': 'corr-194-synthetic' };
    const json = (body: unknown, status = 200) => route.fulfill({ status, headers, contentType: 'application/json', body: JSON.stringify(body) });
    if (request.method() === 'OPTIONS') { await route.fulfill({ status: 204, headers }); return; }
    if (pathname === '/auth/refresh') { await json({ access_token: 'synthetic-token', token_type: 'Bearer', expires_in: 3600, session_id: 'synthetic-session' }); return; }
    if (pathname === '/me') {
      await json({ id: 'synthetic-user', status: 'active', display_name: 'Operador sintético', emails: [], locale: scenario.locale, timezone: 'America/Manaus', notifications: { email: false, in_app: false }, appearance: { density: 'comfortable', font_scale: 'normal' }, avatar: null, permissions: [{ key: 'import.read', organizations: ['synthetic-org'] }], version: 1 }); return;
    }
    if (pathname === '/notifications/unread-count') { await json({ count: 0 }); return; }
    if (pathname === '/imports/synthetic-194') {
      await json({ execution_id: 'synthetic-194', status: 'completed_with_errors', source: 'N-FP', file_name: 'synthetic.csv', started_at: generated, finished_at: generated, failure_reason: null, duplicate_of_execution_id: null }); return;
    }
    if (pathname.endsWith('/result-summary')) {
      await json({ execution_id: 'synthetic-194', execution_status: 'completed_with_errors', summary_status: scenario.availability, summary: scenario.availability === 'ready' ? { rows_read: 3, valid_records: 2, rejected_records: 1, normalized_records: 2, errors: 20, warnings: 35 } : null, issues_total: 55, generated_at: generated, reason_code: scenario.availability === 'ready' ? 'summary_persisted' : 'summary_unavailable', inspection_reason_code: null, duplicate_of_execution_id: null }); return;
    }
    if (pathname.endsWith('/inspections')) { await json([]); return; }
    if (pathname.endsWith('/issues') || pathname.endsWith('/issues/export')) {
      if (scenario.failIssues) { await json({ error: { code: 'import_issues_unavailable', message: 'synthetic private message' } }, 503); return; }
      const severity = url.searchParams.get('severity');
      const rows = Array.from({ length: 55 }, (_, index) => ({ id: index + 1, severity: index < 20 ? 'error' : 'warning', safe_file_name: 'arquivo-1.csv', sheet_name: index ? 'CSV' : null, row_number: index ? index + 2 : null, column_name: index ? 'A' : null, code: 'required_field', reason: 'synthetic-sensitive-cell', scope: 'record', occurred_at: generated })).filter(item => !severity || item.severity === severity);
      if (pathname.endsWith('/export')) {
        await route.fulfill({ status: 200, headers: { ...headers, 'content-disposition': 'attachment; filename="import-issues.csv"' }, contentType: 'text/csv; charset=utf-8', body: '\ufeffid,code\r\n' + rows.map(row => `${row.id},${row.code}\r\n`).join('') }); return;
      }
      const current = Number(url.searchParams.get('page') ?? 1);
      await json({ items: rows.slice((current - 1) * 20, current * 20), pagination: { page: current, page_size: 20, total: rows.length, pages: Math.ceil(rows.length / 20) }, sort: 'oldest', generated_at: generated }); return;
    }
    await json({ error: { code: 'resource_not_found', message: 'Synthetic resource' } }, 404);
  });
}

for (const width of [390, 768, 1440]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`import diagnostics layout and keyboard ${width}px ${theme} (synthetic HTTP)`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 960 });
      await contracts(page, { failIssues: false, availability: 'ready', locale: 'pt-BR' });
      await page.goto('/imports/synthetic-194');
      await expect(page.locator('tbody tr')).toHaveCount(20);
      if (theme === 'dark') await page.locator('.theme-button').click();
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await expect(page.locator('[data-testid="import-counts"] dd')).toHaveCount(6);
      await expect(page.locator('tbody tr').first()).toContainText('Não informado');
      await expect(page.locator('tbody')).not.toContainText('synthetic-sensitive-cell');
      await page.getByLabel('Severidade', { exact: true }).focus();
      await page.keyboard.press('Tab');
      await expect(page.getByRole('button', { name: 'Exportar CSV do filtro' })).toBeFocused();
      const table = page.locator('syn-responsive-table [tabindex="0"]');
      await table.focus();
      if (width === 390) { await table.press('ArrowRight'); await expect.poll(() => table.evaluate(el => el.scrollLeft)).toBeGreaterThan(0); }
      const geometry = await page.locator('.detail-scroll').evaluate(el => ({ overflow: getComputedStyle(el).overflowY, scrollable: el.scrollHeight > el.clientHeight, pageOverflow: document.documentElement.scrollWidth > innerWidth }));
      expect(geometry).toEqual({ overflow: 'auto', scrollable: true, pageOverflow: false });
      await page.evaluate(() => document.fonts.ready);
      const audit = await new AxeBuilder({ page }).analyze();
      await info.attach('axe', { body: JSON.stringify(audit.violations), contentType: 'application/json' });
      expect(audit.violations).toEqual([]);
      await page.locator('.detail-scroll').evaluate(el => { el.scrollTop = 0; });
      const screenshot = info.outputPath(`import-diagnostics-${width}-${theme}.png`);
      await page.screenshot({ path: screenshot });
      await info.attach(`import-diagnostics-${width}-${theme}`, { path: screenshot, contentType: 'image/png' });
    });
  }
}

test('paginates 55 issues, retains URL filters and exports all filtered issues (synthetic HTTP)', async ({ page }) => {
  await contracts(page, { failIssues: false, availability: 'ready', locale: 'pt-BR' });
  await page.goto('/imports/synthetic-194');
  await expect(page.locator('tbody tr')).toHaveCount(20);
  await page.getByRole('button', { name: 'Próxima' }).click();
  await expect(page).toHaveURL(/page=2/);
  await page.getByRole('button', { name: 'Próxima' }).click();
  await expect(page.locator('tbody tr')).toHaveCount(15);
  await page.getByLabel('Severidade', { exact: true }).selectOption('warning');
  await expect(page).toHaveURL(/severity=warning/);
  expect(new URL(page.url()).searchParams.get('page')).toBe('1');
  await expect(page.locator('tbody tr')).toHaveCount(20);
  await page.reload(); await expect(page.getByLabel('Severidade', { exact: true })).toHaveValue('warning');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Exportar CSV do filtro' }).click();
  const download = await downloadEvent; expect(download.suggestedFilename()).toBe('import-issues.csv');
  const stream = await download.createReadStream(); const chunks = [];
  for await (const chunk of stream!) chunks.push(chunk);
  expect(Buffer.concat(chunks).toString('utf8').trim().split('\r\n')).toHaveLength(36);
});

test('recovers issues independently and keeps correlation in copyable technical details (synthetic HTTP)', async ({ page }) => {
  const scenario: Scenario = { failIssues: true, availability: 'ready', locale: 'pt-BR' };
  await contracts(page, scenario); await page.goto('/imports/synthetic-194');
  await expect(page.locator('[data-testid="import-counts"] dd')).toHaveCount(6);
  const section = page.locator('.issues-section');
  await expect(section).toContainText('temporariamente indisponível');
  await expect(section.locator('details')).not.toHaveAttribute('open');
  await section.getByText('Detalhes técnicos', { exact: true }).click();
  await expect(section.getByLabel('ID de correlação', { exact: true })).toHaveValue('corr-194-synthetic');
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: webOrigin });
  await section.getByRole('button', { name: 'Copiar ID de correlação' }).click();
  await expect(section.locator('details').getByRole('status')).toContainText('ID de correlação copiado');
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('corr-194-synthetic');
  scenario.failIssues = false;
  await section.getByRole('button', { name: 'Tentar consulta novamente' }).click();
  await expect(page.locator('tbody tr')).toHaveCount(20);
  await expect(page.locator('[data-testid="import-counts"] dd')).toHaveCount(6);
});

test('terminal summary absence is unavailable and localized in English (synthetic HTTP)', async ({ page }) => {
  await contracts(page, { failIssues: false, availability: 'unavailable', locale: 'en-US' });
  await page.goto('/imports/synthetic-194');
  await expect(page.locator('.summary-section')).toContainText('No persisted counts are available');
  await expect(page.locator('.summary-section')).not.toContainText('Processing is in progress');
  await expect(page.locator('tbody')).toContainText('Empty required field');
});
