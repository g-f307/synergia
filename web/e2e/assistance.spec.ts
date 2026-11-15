import AxeBuilder from '@axe-core/playwright';
import { expect, test, Page, TestInfo } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import Ajv from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let executions: Record<'ready' | 'insufficient' | 'rejected', string>;
const python = process.env.E2E_PYTHON ?? 'python';
const api = `http://127.0.0.1:${process.env.E2E_AI_API_PORT ?? '8001'}`;
const buttonName = /gerar análise assistida|generate assisted analysis/i;

async function login(page: Page, email = 'manager.e2e@example.invalid') {
  execFileSync(python, ['../scripts/bootstrap_web_e2e.py', '--revoke-email', email]);
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => sessionStorage.clear());
  await page.reload();
  await page.getByLabel(/e-mail|email/i).fill(email);
  await page.getByLabel(/senha|password/i).fill(process.env.E2E_PASSWORD ?? 'synthetic-e2e-password-63');
  await page.getByRole('button', { name: /entrar|sign in/i }).click();
  await expect(page).toHaveURL(/\/profile/);
}
async function open(page: Page, id = executions.ready) {
  await page.goto(`/executions/${id}`);
  await expect(page.locator('.summary-highlights')).toBeVisible();
  await expect(page.locator('.assistance')).toBeVisible();
}
async function screenshotAndAxe(page: Page, info: TestInfo, name: string) {
  const card = page.locator('.assistance');
  await card.evaluate(element => {
    const scroll = element.closest('.detail-scroll');
    if (scroll) scroll.scrollTop += element.getBoundingClientRect().top - scroll.getBoundingClientRect().top - 64;
  });
  const screenshotPath = info.outputPath(`${name}-page.png`);
  if (await page.evaluate(() => devicePixelRatio > 1)) {
    // Native viewport capture avoids clipping physical pixels to CSS dimensions
    // when real browser zoom changes DPR. The page layout stays untouched.
    const protocol = await page.context().newCDPSession(page);
    try {
      const capture = await protocol.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
      await writeFile(screenshotPath, Buffer.from(capture.data, 'base64'));
    } finally { await protocol.detach(); }
  } else await page.screenshot({ path: screenshotPath });
  const results = await new AxeBuilder({ page }).include('.assistance').analyze();
  const reportPath = info.outputPath(`axe-${name}.json`);
  await writeFile(reportPath, JSON.stringify(results, null, 2));
  await info.attach(`axe-${name}`, { path: reportPath, contentType: 'application/json' });
  expect(results.violations).toEqual([]);
  expect(await card.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
}

test.describe.serial('execution assistance with real API and controlled provider', () => {
  test.beforeAll(() => {
    executions = JSON.parse(execFileSync(python, ['../scripts/serve_assistance_e2e.py', '--seed'], {
      env: { ...process.env, SYNERGIA_ENV: 'test' }, encoding: 'utf8',
    }));
  });
  test('generates only on explicit action, validates contract and reads the persisted result without inference', async ({ page, request }, info) => {
    await login(page);
    const generated: string[] = [];
    page.on('request', req => { if (req.method() === 'POST' && req.url().endsWith('/ai-assistance')) generated.push(req.url()); });
    await open(page);
    await expect(page.getByRole('button', { name: buttonName })).toBeVisible();
    expect(generated).toHaveLength(0);
    await screenshotAndAxe(page, info, 'empty-desktop-light');
    const highlights = page.locator('.summary-highlights');
    expect(await highlights.evaluate(el => el.nextElementSibling?.tagName)).toBe('SYN-EXECUTION-ASSISTANCE');
    const response = page.waitForResponse(res => res.url().endsWith('/ai-assistance') && res.request().method() === 'POST');
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/executions/*/ai-assistance', async route => { await gate; await route.continue(); });
    try {
      const button = page.locator('.assistance button').first();
      await button.click(); await expect(button).toBeDisabled();
      await button.evaluate(element => (element as HTMLButtonElement).click());
      await expect(page.locator('.assistance-status')).toHaveText(/gerando análise|generating analysis/i);
      await screenshotAndAxe(page, info, 'generating-desktop-light');
    } finally { release(); }
    const generatedResponse = await response; expect(generatedResponse.status()).toBe(200);
    const result = await generatedResponse.json();
    expect(result.state).toBe('ready'); expect(result.provenance.origin).toBe('model');
    const schema = await (await request.get(`${api}/openapi.json`)).json();
    const ajv = new Ajv({ strict: false }); addFormats(ajv);
    const validate = ajv.compile({ $ref: '#/components/schemas/AiAssistanceResponse', components: schema.components });
    expect(validate(result), JSON.stringify(validate.errors)).toBe(true);
    await expect(page.locator('.assistance-status')).toHaveText(/análise pronta|analysis ready/i);
    await expect(page.locator('.assistance .limitations')).toBeVisible();
    await expect(page.getByRole('button', { name: buttonName })).toHaveCount(0);
    await screenshotAndAxe(page, info, 'ready-desktop-light');
    await page.reload();
    await expect(page.locator('.assistance-summary')).toHaveText(result.summary);
    expect(generated).toHaveLength(1);
    const visible = await page.locator('.assistance').textContent();
    for (const secret of ['controlled-e2e', result.provenance.digest, result.provenance.prompt_hash, result.provenance.context_hash, '11434']) expect(visible).not.toContain(secret);
  });
  test('navigates by keyboard to a reference and preserves URL filters without inventing highlights', async ({ page }, info) => {
    await login(page);
    await page.goto(`/executions/${executions.ready}?tab=summary&severity=error&source=N-FP&page=4&from=%2Fexecutions%3Fpage%3D2`);
    const link = page.locator('.assistance .references a').filter({ hasText: /^DIV-/ }).first();
    await expect(link).toBeVisible(); const reference = await link.textContent();
    await link.focus(); await expect(link).toBeFocused(); await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/tab=divergences/);
    const url = new URL(page.url());
    expect(url.searchParams.get('reference')).toBe(reference);
    expect(url.searchParams.get('page')).toBe('1'); expect(url.searchParams.get('severity')).toBe('error');
    expect(url.searchParams.get('source')).toBe('N-FP'); expect(url.searchParams.get('from')).toBe('/executions?page=2');
    await expect(page.locator('.reference-location')).toContainText(reference!);
    await expect(page.locator('.records article')).toHaveCount(1);
    await expect(page.locator('.records [aria-selected="true"]')).toHaveCount(0);
    await page.screenshot({ path: info.outputPath('reference-navigation.png'), fullPage: true });
    await page.goBack(); // browser history must not lose the reference destination
  });
  test('shows insufficient evidence and deterministic fallback from the real backend', async ({ page }, info) => {
    await login(page);
    for (const [name, state] of [['insufficient', 'insufficient_evidence'], ['rejected', 'rejected']] as const) {
      await open(page, executions[name]);
      const response = page.waitForResponse(res => res.url().endsWith('/ai-assistance') && res.request().method() === 'POST');
      await page.getByRole('button', { name: buttonName }).click();
      const generatedResponse = await response; expect(generatedResponse.status()).toBe(200);
      expect((await generatedResponse.json()).state).toBe(state);
      await expect(page.locator('.assistance syn-badge')).toHaveText(/resumo determinístico|deterministic summary/i);
      await expect(page.locator('.limitations')).toBeVisible();
      await screenshotAndAxe(page, info, name);
    }
  });
  test('keeps execution data usable when assistance runtime is unavailable', async ({ page }, info) => {
    await login(page);
    await page.route('**/executions/*/ai-assistance/latest', route => route.fulfill({ status: 503, json: { error: { code: 'ai_assistance_runtime_unavailable' } } }));
    await open(page);
    await expect(page.locator('.assistance-status')).toHaveText(/assistência indisponível|assistance unavailable/i);
    await expect(page.locator('.summary-groups')).toBeVisible();
    await screenshotAndAxe(page, info, 'unavailable');
    await page.getByRole('button', { name: /histórico|history/i, exact: true }).click();
    await expect(page.locator('.history')).toBeVisible();
  });
  test('hides assistance without permissions and when feature is disabled', async ({ page }) => {
    await login(page, 'operator.e2e@example.invalid');
    await page.goto(`/executions/${executions.ready}`);
    await expect(page.locator('.summary-highlights')).toBeVisible();
    await expect(page.locator('.assistance')).toHaveCount(0);
    await login(page);
    await page.route('**/me/ai-assistance-capability', route => route.fulfill({ json: { enabled: false, read: false, generate: false } }));
    await page.goto(`/executions/${executions.ready}`);
    await expect(page.locator('.summary-highlights')).toBeVisible(); await expect(page.locator('.assistance')).toHaveCount(0);
  });
  test('reflows at actual 250% browser zoom in both themes', async ({ browser }, info) => {
    const profile = await mkdtemp(join(tmpdir(), 'synergia-assistance-zoom-'));
    await mkdir(join(profile, 'Default'));
    // Chrome's persisted partition zoom preference, in logarithmic zoom levels.
    // Assert DPR and layout width below so a changed preference cannot silently
    // turn this into a CSS zoom or a no-op test.
    await writeFile(join(profile, 'Default', 'Preferences'), JSON.stringify({
      partition: { default_zoom_level: { x: Math.log(2.5) / Math.log(1.2) } },
    }));
    const context = await browser.browserType().launchPersistentContext(profile, {
      ...(process.env.E2E_BROWSER_CHANNEL ? { channel: process.env.E2E_BROWSER_CHANNEL } : {}),
      ...(process.env.E2E_BROWSER_EXECUTABLE_PATH ? { executablePath: process.env.E2E_BROWSER_EXECUTABLE_PATH } : {}),
      headless: true, viewport: null, deviceScaleFactor: undefined, baseURL: info.project.use.baseURL,
      args: ['--window-size=1440,1000'],
    });
    try {
      const page = await context.newPage(); await login(page); await open(page);
      const metrics = await page.evaluate(() => ({ width: innerWidth, height: innerHeight, dpr: devicePixelRatio, cssZoom: getComputedStyle(document.documentElement).zoom }));
      expect(metrics.dpr).toBeCloseTo(2.5); expect(metrics.width).toBeLessThanOrEqual(576); expect(metrics.cssZoom).toBe('1');
      await info.attach('browser-zoom-metrics', { body: JSON.stringify(metrics), contentType: 'application/json' });
      for (const theme of ['light', 'dark']) {
        await page.evaluate(value => { document.documentElement.dataset['theme'] = value; }, theme);
        await screenshotAndAxe(page, info, `zoom-250-${theme}`);
      }
    } finally { await context.close(); await rm(profile, { recursive: true, force: true }); }
  });
  test('supports long text, light/dark themes, reduced motion and mobile/tablet', async ({ page }, info) => {
    test.setTimeout(120_000);
    await login(page);
    for (const scenario of ['ready', 'insufficient', 'unavailable'] as const) {
      if (scenario === 'unavailable') await page.route('**/executions/*/ai-assistance/latest', route => route.fulfill({ status: 503, json: { error: { code: 'ai_assistance_runtime_unavailable' } } }));
      for (const theme of ['light', 'dark']) {
        for (const width of [390, 768, 1440]) {
          await page.setViewportSize({ width, height: 1000 });
          await page.emulateMedia({ reducedMotion: 'reduce' });
          await open(page, scenario === 'insufficient' ? executions.insufficient : executions.ready);
          await page.evaluate(value => { document.documentElement.dataset['theme'] = value; }, theme);
          await expect(page.locator('.assistance-status')).toHaveText(scenario === 'ready' ? /análise pronta|analysis ready/i : scenario === 'insufficient' ? /evidências insuficientes|insufficient evidence/i : /assistência indisponível|assistance unavailable/i);
          await screenshotAndAxe(page, info, `${scenario}-${theme}-${width}`);
        }
      }
    }
    await page.unroute('**/executions/*/ai-assistance/latest');
    await page.route('**/executions/*/ai-assistance/latest', async route => {
      const response = await route.fetch(); const result = await response.json();
      result.summary = 'Conferência humana necessária. '.repeat(20).slice(0, 600);
      result.findings = Array.from({ length: 5 }, (_, index) => ({ title: 'Achado longo '.repeat(10).slice(0, 120), explanation: 'Há registros disponíveis para conferência. '.repeat(15).slice(0, 600), evidence_refs: [`DIV-long-${index}`] }));
      result.human_checks = Array(3).fill('Conferência humana das referências disponíveis. '.repeat(12).slice(0, 600));
      result.limitations = Array(5).fill('Há dados ausentes ou indisponíveis no contexto. '.repeat(12).slice(0, 600));
      await route.fulfill({ response, json: result });
    });
    await page.setViewportSize({ width: 390, height: 844 }); await open(page);
    await expect(page.locator('.assistance .findings>li')).toHaveCount(5);
    await screenshotAndAxe(page, info, 'long-mobile');
  });
});
