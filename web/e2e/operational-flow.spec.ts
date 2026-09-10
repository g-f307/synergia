import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

const operatorEmail = 'operator.e2e@example.invalid';
const readerEmail = 'reader.e2e@example.invalid';
const managerEmail = 'manager.e2e@example.invalid';
const managerId = '63000000-0000-4000-8000-000000000003';
const password = process.env.E2E_PASSWORD ?? 'synthetic-e2e-password-63';
const fixture = path.resolve('../data/synthetic/fixtures/minimal-comprehensive/n-fp.xlsx');
const qualityFixture = path.resolve('../data/synthetic/fixtures/minimal-comprehensive/gmes-oqc.csv');
let executionId = '';
let pendingId = '';

function revokeSessions(email: string) {
  execFileSync(process.env.E2E_PYTHON ?? 'python', ['../scripts/bootstrap_web_e2e.py', '--revoke-email', email], {
    cwd: process.cwd(), env: process.env,
  });
}

async function login(page: import('@playwright/test').Page, email = operatorEmail) {
  revokeSessions(email);
  await page.goto('/login');
  await page.getByLabel(/e-mail|email/i).fill(email);
  await page.getByLabel(/senha|password/i).fill(password);
  await page.getByRole('button', { name: /entrar|sign in/i }).click();
  await expect(page).toHaveURL(/\/profile/);
}

async function openPending(page: import('@playwright/test').Page) {
  await page.locator('a[href="/pending-items"]').click();
  await page.locator(`a[href^="/pending-items/${pendingId}"]`).click();
  await expect(page).toHaveURL(new RegExp(`/pending-items/${pendingId}`));
}

async function expectAccessible(
  page: import('@playwright/test').Page,
  testInfo: import('@playwright/test').TestInfo,
  label: string,
) {
  const results = await new AxeBuilder({ page }).analyze();
  await testInfo.attach(`axe-${label}`, {
    body: Buffer.from(JSON.stringify(results, null, 2)), contentType: 'application/json',
  });
  expect(results.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? ''))).toEqual([]);
}

test.describe.serial('integrated operational journey', () => {
  test('login, upload and execution use the real API and homologated fixture', async ({ page }, testInfo) => {
    const exposed: string[] = [];
    const responseBodies: Promise<string>[] = [];
    page.on('console', (message) => exposed.push(message.text()));
    page.on('response', (response) => {
      if (response.url().startsWith('http://127.0.0.1:8000/') && !response.url().includes('/auth/')) {
        responseBodies.push(response.text().catch(() => ''));
      }
    });
    await login(page);
    await expectAccessible(page, testInfo, 'profile-desktop');
    await page.locator('a[href="/imports/new"]').click();
    await page.getByLabel(/arquivo|file/i).setInputFiles(fixture);
    await page.getByRole('button', { name: /enviar|upload/i }).click();
    await expect(page).toHaveURL(/\/imports\/[0-9a-f-]+/, { timeout: 30_000 });
    executionId = page.url().split('/').pop() ?? '';
    await expect(page.getByText(executionId).first()).toBeVisible();
    await page.locator('a[href="/executions"]').first().click();
    await page.getByLabel(/identificador da execução|execution identifier/i).fill(executionId);
    await page.getByRole('button', { name: /localizar|locate/i }).click();
    await expect(page.getByText(executionId).first()).toBeVisible();

    await page.locator('a[href="/imports/new"]').click();
    await page.getByLabel(/fonte|source/i).selectOption('GMES/OQC');
    await page.getByLabel(/arquivo|file/i).setInputFiles(qualityFixture);
    await page.getByRole('button', { name: /enviar|upload/i }).click();
    await expect(page).toHaveURL(/\/imports\/[0-9a-f-]+/, { timeout: 30_000 });
    const observableOutput = `${exposed.join('\n')}\n${(await Promise.all(responseBodies)).join('\n')}`;
    expect(observableOutput).not.toMatch(
      /eyJ[A-Za-z0-9_-]+\.eyJ|storage[_-]?path|local_password_hash|password|[A-Z]:\\Users\\/i,
    );
  });

  test('shows internal notifications and persists individual and batch reads', async ({ page }, testInfo) => {
    await login(page);
    const trigger = page.locator('a.notification-button');
    await expect(trigger).toHaveAttribute('aria-label', /[1-9]\d* (não lidas|unread)/i);
    await trigger.click();
    await expect(page).toHaveURL(/\/notifications/);
    await expect(page.locator('.notification-list li').first()).toBeVisible();
    await expectAccessible(page, testInfo, 'notifications-desktop');
    await testInfo.attach('notifications-desktop', {
      body: await page.screenshot({ fullPage: true }), contentType: 'image/png',
    });
    await page.getByRole('button', { name: /marcar como lida|mark as read/i }).first().click();
    await page.getByRole('button', { name: /marcar todas como lidas|mark all as read/i }).click();
    await expect(page.getByRole('button', { name: /marcar todas como lidas|mark all as read/i })).toBeDisabled();
    await login(page);
    await page.locator('input[formcontrolname="email"]').uncheck();
    await page.locator('input[formcontrolname="in_app"]').uncheck();
    await page.getByRole('button', { name: /salvar|save/i }).click();
    await expect(page.getByRole('status')).toBeVisible();
    await page.reload();
    await login(page);
    await expect(page.locator('input[formcontrolname="email"]')).not.toBeChecked();
    await expect(page.locator('input[formcontrolname="in_app"]')).not.toBeChecked();
    await page.locator('input[formcontrolname="email"]').check();
    await page.locator('input[formcontrolname="in_app"]').check();
    await page.getByRole('button', { name: /salvar|save/i }).click();
  });

  test('generates, views and safely exports a persisted report', async ({ page }, testInfo) => {
    await login(page, managerEmail);
    await page.locator('a[href="/reports"]').click();
    await page.getByRole('button', { name: /generate report/i }).click();
    const generationDialog = page.getByRole('dialog', {
      name: /new report generation|nova geração de relatório/i,
    });
    await expect(generationDialog).toBeVisible();
    await generationDialog.getByLabel(/organization|organização/i).selectOption({ index: 1 });
    await generationDialog.getByLabel(/execution|execução/i).fill(executionId);
    const reportCreated = page.waitForResponse((response) =>
      response.url().endsWith('/reports') && response.request().method() === 'POST',
    );
    await generationDialog.getByRole('button', { name: /generate report|gerar relatório/i }).click();
    expect((await reportCreated).status()).toBe(201);
    await expect(page).toHaveURL(/\/reports\/[0-9a-f-]+\?/, { timeout: 30_000 });
    await expect(page.getByRole('heading', { name: /report viewer/i })).toBeVisible();
    await expect(page.getByText(executionId).first()).toBeVisible();
    await expectAccessible(page, testInfo, 'report-detail-desktop');

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /exportar|export/i }).click();
    const download = await downloadPromise;
    const exportPath = await download.path();
    expect(exportPath).toBeTruthy();
    const exportBody = await import('node:fs').then(({ readFileSync }) => readFileSync(exportPath!, 'utf8'));
    expect(exportBody).toContain('SYN-WO-000001');
    expect(exportBody.split(/\r?\n/).some((line) => /^[=+@]/.test(line))).toBe(false);
    await testInfo.attach('stage-4-safe-report.csv', { body: Buffer.from(exportBody), contentType: 'text/csv' });
    await testInfo.attach('report-detail-desktop', {
      body: await page.screenshot({ fullPage: true }), contentType: 'image/png',
    });
  });

  test('consults the resulting Workorder and expected pending queue', async ({ page }, testInfo) => {
    await login(page);
    await page.locator('a[href="/search"]').click();
    await page.getByRole('searchbox', { name: /identificador|identifier/i }).fill('SYN-WO-000001');
    await page.getByRole('button', { name: /buscar|pesquisar|search/i }).click();
    await expect(page.getByText('SYN-WO-000001').first()).toBeVisible();
    await page.locator('a[href="/pending-items"]').click();
    await expect(page.locator('tbody tr').first()).toBeVisible();
    await page.locator('tbody tr a').first().click();
    await expect(page).toHaveURL(/\/pending-items\/\d+/);
    pendingId = page.url().match(/pending-items\/(\d+)/)?.[1] ?? '';
    await page.getByLabel(/justificativa|justification/i).fill('E2E: submit for human decision.');
    await page.getByRole('button', { name: /enviar para|submit for review/i }).click();
    await expect(page.locator('.approval dl .badge').first()).toContainText(/enviada|submitted/i);
    await expectAccessible(page, testInfo, 'pending-detail-desktop');
    await testInfo.attach('pending-detail-desktop', {
      body: await page.screenshot({ fullPage: true }), contentType: 'image/png',
    });
  });

  test('assigns, returns, resubmits and approves with segregation of duties', async ({ page }, testInfo) => {
    await login(page, managerEmail);
    await openPending(page);
    await expect(page.locator('.approval dl .badge').first()).toContainText(/submitted/i);
    await page.getByLabel(/assignee/i).fill(managerId);
    await page.getByLabel(/justification/i).fill('E2E: assignment to authorized manager.');
    await page.getByRole('button', { name: /assign review/i }).click();
    await expect(page.locator('.approval dl .badge').first()).toContainText(/in review/i);
    await page.getByLabel(/justification/i).last().fill('E2E: return for additional evidence.');
    await page.getByRole('button', { name: /return for correction/i }).click();
    await expect(page.locator('.approval dl .badge').first()).toContainText(/returned/i);

    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await login(page, operatorEmail);
    await openPending(page);
    await expect(page.locator('.approval dl .badge').first()).toContainText(/devolvida|returned/i);
    await page.getByLabel(/justificativa|justification/i).last().fill('E2E: additional evidence supplied.');
    const resubmitted = page.waitForResponse((response) =>
      response.url().includes('/approvals/') && response.url().endsWith('/resubmit'),
    );
    await page.getByRole('button', { name: /reenviar para|resubmit for review/i }).click();
    expect((await resubmitted).status()).toBe(200);
    await expect(page.locator('.approval dl .badge').first()).toContainText(/enviada|submitted/i);

    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await login(page, managerEmail);
    await openPending(page);
    await expect(page.locator('.approval dl .badge').first()).toContainText(/submitted/i);
    await page.getByLabel(/assignee/i).fill(managerId);
    await page.getByLabel(/justification/i).fill('E2E: reassignment after correction.');
    await page.getByRole('button', { name: /assign review/i }).click();
    await expect(page.locator('.approval dl .badge').first()).toContainText(/in review/i);
    await page.getByLabel(/justification/i).last().fill('E2E: evidence verified and approved.');
    await page.getByLabel(/confirmo conscientemente|consciously confirm/i).check();
    const approved = page.waitForResponse((response) =>
      response.url().includes('/approvals/') && response.url().endsWith('/approve'),
    );
    await page.getByRole('button', { name: /^aprovar$|^approve$/i }).click();
    expect((await approved).status()).toBe(200);
    await expect(page.locator('.approval dl .badge').first()).toContainText(/approved/i);
    await expect(page.locator('ol.timeline li')).toHaveCount(6);
    await expectAccessible(page, testInfo, 'approval-history-desktop');
    await testInfo.attach('approval-history-desktop', {
      body: await page.screenshot({ fullPage: true }), contentType: 'image/png',
    });

    const capturePath = testInfo.outputPath('stage-4-email-capture.jsonl');
    const deliveryEnvironment = {
      ...process.env,
      EMAIL_DELIVERY_ENABLED: 'true', EMAIL_PROVIDER: 'local_capture',
      EMAIL_FROM_ADDRESS: 'no-reply.e2e@example.invalid', EMAIL_CAPTURE_PATH: capturePath,
      EMAIL_CONSOLIDATION_SECONDS: '0',
    };
    execFileSync(process.env.E2E_PYTHON ?? 'python', ['../scripts/process_email_notifications.py'], {
      cwd: process.cwd(), env: deliveryEnvironment,
    });
    execFileSync(process.env.E2E_PYTHON ?? 'python', ['../scripts/process_email_notifications.py'], {
      cwd: process.cwd(), env: deliveryEnvironment,
    });
    const messages = await import('node:fs').then(({ readFileSync }) => readFileSync(capturePath, 'utf8')
      .trim().split(/\r?\n/).map((line) => JSON.parse(line)));
    expect(messages.length).toBeGreaterThan(0);
    expect(new Set(messages.map((message) => message.delivery_id)).size).toBe(messages.length);
    const captured = JSON.stringify(messages);
    expect(captured).not.toMatch(/eyJ[A-Za-z0-9_-]+\.eyJ|local_password_hash|password|storage[_-]?path/i);
    await testInfo.attach('stage-4-email-capture.jsonl', {
      body: Buffer.from(messages.map((message) => JSON.stringify(message)).join('\n')),
      contentType: 'application/x-ndjson',
    });
  });

  test('covers rejected upload and temporary API recovery', async ({ page }) => {
    await login(page);
    await page.locator('a[href="/imports/new"]').click();
    await page.getByLabel(/arquivo|file/i).setInputFiles({ name: 'invalid.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('not an xlsx') });
    await page.getByRole('button', { name: /enviar|upload/i }).click();
    await expect(page.getByRole('status')).toContainText(/rejeitado|rejected/i);

    let failed = false;
    await page.route('**/pending-items?**', async (route) => {
      if (!failed) { failed = true; await route.abort('connectionfailed'); }
      else await route.continue();
    });
    await page.locator('a[href="/pending-items"]').click();
    await expect(page.getByText(/indisponível|unavailable/i).first()).toBeVisible();
    await page.locator('a[href="/profile"]').first().click();
    await page.locator('a[href="/pending-items"]').click();
    await expect(page.locator('section.results')).toBeVisible();
  });

  test('expires a persisted session and redirects without leaking the resource', async ({ page }) => {
    await login(page);
    revokeSessions(operatorEmail);
    await page.goto('/pending-items');
    await expect(page).toHaveURL(/\/login/);
  });

  test('enforces role and organization scope', async ({ page }) => {
    await login(page, readerEmail);
    await expect(page.getByRole('link', { name: /new import|nova importação/i })).toHaveCount(0);
    await page.locator('a[href="/search"]').click();
    await page.getByRole('searchbox', { name: /identifier|identificador/i }).fill('SYN-WO-000001');
    await page.getByRole('button', { name: /search|buscar|pesquisar/i }).click();
    await expect(page.getByText(/nenhum resultado|no results/i)).toBeVisible();
  });

  test('supports English, keyboard navigation and a mobile viewport', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/login');
    await page.getByLabel(/idioma|language/i).selectOption('en-US');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Sign in');
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await expect(page.locator(':focus')).toBeVisible();
    await login(page, readerEmail);
    await expect(page.locator('html')).toHaveAttribute('lang', 'en-US');
    await expectAccessible(page, testInfo, 'profile-mobile-en');
    await testInfo.attach('profile-mobile-en', {
      body: await page.screenshot({ fullPage: true }), contentType: 'image/png',
    });
  });
});
