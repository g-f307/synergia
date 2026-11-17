import AxeBuilder from '@axe-core/playwright';
import { expect, test, Page, TestInfo } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import Ajv from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let executions: Record<'ready' | 'insufficient' | 'rejected', string>;
const python = process.env.E2E_PYTHON ?? 'python';
const api = `http://127.0.0.1:${process.env.E2E_AI_API_PORT ?? '8001'}`;
const counterFile = process.env.E2E_PROVIDER_COUNTER_FILE;
if (!counterFile) {
  throw new Error('E2E_PROVIDER_COUNTER_FILE must be set');
}
const buttonName = /gerar análise assistida|generate assisted analysis/i;

async function readProviderCalls(): Promise<number> {
  const raw = await readFile(counterFile!, 'utf8');
  const parsed = JSON.parse(raw);
  if (typeof parsed?.calls !== 'number') {
    throw new Error(`Invalid provider counter payload in ${counterFile}`);
  }
  return parsed.calls;
}

async function loginAndCaptureBearer(page: Page, email: string): Promise<string> {
  let bearer = '';
  const listener = (req: import('@playwright/test').Request) => {
    const auth = req.headers()['authorization'];
    if (auth?.startsWith('Bearer ')) {
      bearer = auth;
    }
  };
  page.on('request', listener);
  try {
    await login(page, email);
    await expect.poll(() => bearer).not.toBe('');
    return bearer;
  } finally {
    page.off('request', listener);
  }
}

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

  test('completes real import journey, idempotent reuse by provider counter, and org B isolation', async ({ page, request }, info) => {
    const orgABearer = await loginAndCaptureBearer(page, 'manager.e2e@example.invalid');
    await page.goto('/imports/new');
    await page.getByLabel(/fonte|source/i).selectOption('Total Decision');
    const fileInput = page.locator('#import-file');
    await expect(fileInput).toHaveAttribute('accept', '.xlsx');
    await fileInput.setInputFiles('../data/synthetic/total-decision_minimal.xlsx');
    await page.getByRole('button', { name: /enviar|upload/i }).click();
    await expect(page).toHaveURL(/\/imports\/[0-9a-f-]+/, { timeout: 30_000 });
    const importedExecutionId = page.url().split('/').pop()?.split('?')[0] ?? '';
    expect(importedExecutionId).toMatch(/^[0-9a-f-]{36}$/);

    await expect.poll(async () => {
      const res = await request.get(`${api}/executions/${importedExecutionId}`, {
        headers: { Authorization: orgABearer },
      });
      if (!res.ok()) return 'pending';
      const body = await res.json();
      return body.status;
    }, { timeout: 30_000 }).toMatch(/^(completed|completed_with_errors|failed|validation_failed)$/);

    await page.getByTestId('related-execution').click();
    await expect(page).toHaveURL(new RegExp(`/executions/${importedExecutionId}`));
    await expect(page.locator('.summary-highlights')).toBeVisible();
    await expect(page.locator('.assistance')).toBeVisible();

    const callsBefore = await readProviderCalls();
    const generateResponse = page.waitForResponse(res => res.url().endsWith('/ai-assistance') && res.request().method() === 'POST');
    await page.getByRole('button', { name: buttonName }).click();
    const generated = await generateResponse;
    expect(generated.status()).toBe(200);
    const payload = await generated.json();
    expect(payload.execution_id).toBe(importedExecutionId);
    expect(payload.summary).toBeTruthy();
    expect(payload.provenance).toBeDefined();
    expect(Array.isArray(payload.limitations)).toBe(true);
    const callsAfterFirst = await readProviderCalls();
    expect(callsAfterFirst).toBe(callsBefore + 1);

    await page.reload();
    await expect(page.locator('.assistance-summary')).toHaveText(payload.summary);
    const repeatRes = await request.post(`${api}/executions/${importedExecutionId}/ai-assistance`, {
      headers: { Authorization: orgABearer, 'Content-Type': 'application/json' },
      data: {},
    });
    expect(repeatRes.status()).toBe(200);
    const repeatPayload = await repeatRes.json();
    expect(repeatPayload.assistance_id).toBe(payload.assistance_id);
    expect(repeatPayload.summary).toBe(payload.summary);
    expect(await readProviderCalls()).toBe(callsAfterFirst);
    await screenshotAndAxe(page, info, 'real-import-ready');

    const orgBBearer = await loginAndCaptureBearer(page, 'manager-b.e2e@example.invalid');
    await page.goto(`/executions/${importedExecutionId}`);
    await expect(page.locator('.assistance-summary')).toHaveCount(0);
    const orgBGet = await request.get(`${api}/executions/${importedExecutionId}/ai-assistance/latest`, {
      headers: { Authorization: orgBBearer },
    });
    expect(orgBGet.status()).toBe(404);
    expect(await orgBGet.text()).not.toContain(payload.summary);
    const orgBPost = await request.post(`${api}/executions/${importedExecutionId}/ai-assistance`, {
      headers: { Authorization: orgBBearer, 'Content-Type': 'application/json' },
      data: {},
    });
    expect(orgBPost.status()).toBe(404);
    expect(await orgBPost.text()).not.toContain(importedExecutionId);
  });
});
