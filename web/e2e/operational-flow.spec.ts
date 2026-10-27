import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

const operatorEmail = 'operator.e2e@example.invalid';
const readerEmail = 'reader.e2e@example.invalid';
const managerEmail = 'manager.e2e@example.invalid';
const adminEmail = 'admin.e2e@example.invalid';
const managerId = '63000000-0000-4000-8000-000000000003';
const password = process.env.E2E_PASSWORD ?? 'synthetic-e2e-password-63';
const fixture = path.resolve('../data/synthetic/fixtures/minimal-comprehensive/n-fp.xlsx');
const qualityFixture = path.resolve('../data/synthetic/fixtures/minimal-comprehensive/gmes-oqc.csv');
const woStatusFixture = path.resolve('../data/synthetic/ingestion-v1/wo-composite.xlsx');
const totalDecisionFixture = path.resolve('../data/synthetic/ingestion-v1/td-edge.xlsx');
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

function approvalState(page: import('@playwright/test').Page) {
  return page.getByRole('region', { name: /decisão humana|human decision/i })
    .locator('.approval-metadata .status-pill').first();
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
  test('revokes another browser session and blocks its next authenticated request', async ({ browser, page }) => {
    test.setTimeout(60_000);
    await login(page);
    const secondContext = await browser.newContext();
    try {
      const secondPage = await secondContext.newPage();
      await secondPage.goto('/login');
      await secondPage.getByLabel(/e-mail|email/i).fill(operatorEmail);
      await secondPage.getByLabel(/senha|password/i).fill(password);
      await secondPage.getByRole('button', { name: /entrar|sign in/i }).click();
      await expect(secondPage).toHaveURL(/\/profile/);
      await page.getByRole('button', { name: /atualizar|refresh sessions/i }).click();
      await expect(page.locator('.session-list li')).toHaveCount(2);
      await page.getByRole('button', { name: /encerrar outras|end other sessions/i }).click();
      const confirmation = page.getByRole('dialog');
      await expect(confirmation).toBeVisible();
      await confirmation.getByRole('button', { name: /confirmar|confirm/i }).click();
      await expect(page.locator('.session-list li')).toHaveCount(1);
      await secondPage.reload();
      await expect(secondPage).toHaveURL(/\/login/);
    } finally {
      await secondContext.close();
    }
  });

  test('login, upload and execution use the real API and homologated fixture', async ({ page }, testInfo) => {
    const browserSession = await page.context().newCDPSession(page);
    await browserSession.send('Emulation.setTimezoneOverride', { timezoneId: 'America/Manaus' });
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
    const fileInput = page.locator('#import-file');
    await expect(fileInput).toBeEnabled();
    await fileInput.setInputFiles(fixture);
    await page.getByRole('button', { name: /enviar|upload/i }).click();
    await expect(page).toHaveURL(/\/imports\/[0-9a-f-]+/, { timeout: 30_000 });
    executionId = page.url().split('/').pop() ?? '';
    await expect(page.getByText(executionId).first()).toBeVisible();
    await page.locator('a[href="/executions"]').first().click();
    await page.locator('details.catalog-filters > summary').click();
    await page.getByLabel(/identificador da execução|execution identifier/i).fill(executionId);
    await page.getByLabel(/início do período|period start/i).fill('2026-09-01T08:30');
    const filteredCatalogRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith('/executions') && url.searchParams.get('execution_id') === executionId;
    });
    await page.getByRole('button', { name: /aplicar filtros|apply filters/i }).click();
    expect(new URL((await filteredCatalogRequest).url()).searchParams.get('date_from'))
      .toBe('2026-09-01T12:30:00.000Z');
    await expect(page).toHaveURL(new RegExp(`/executions\\?.*execution_id=${executionId}`));
    await page.locator('button.execution-row').filter({ hasText: executionId }).click();
    await expect(page).toHaveURL(new RegExp(`/executions/${executionId}`));
    await expect(page.getByText(executionId).first()).toBeVisible();
    await page.getByRole('button', { name: /voltar ao monitor|back to monitor/i }).click();
    await expect(page).toHaveURL(new RegExp(`/executions\\?.*execution_id=${executionId}`));
    await testInfo.attach('execution-catalog-context-desktop', {
      body: await page.screenshot({ fullPage: true }), contentType: 'image/png',
    });

    await page.locator('a[href="/imports/new"]').click();
    await page.getByLabel(/fonte|source/i).selectOption('GMES/OQC');
    const qualityFileInput = page.locator('#import-file');
    await expect(qualityFileInput).toBeEnabled();
    await qualityFileInput.setInputFiles(qualityFixture);
    await page.getByRole('button', { name: /enviar|upload/i }).click();
    await expect(page).toHaveURL(/\/imports\/[0-9a-f-]+/, { timeout: 30_000 });
    const observableOutput = `${exposed.join('\n')}\n${(await Promise.all(responseBodies)).join('\n')}`;
    expect(observableOutput).not.toMatch(
      /eyJ[A-Za-z0-9_-]+\.eyJ|storage[_-]?path|local_password_hash|password|[A-Z]:\\Users\\/i,
    );
  });

  test('imports the real workbook families and keeps duplicate uploads idempotent', async ({ page }) => {
    await login(page);
    const imports = [
      { source: 'WO Status', workbook: woStatusFixture },
      { source: 'Total Decision', workbook: totalDecisionFixture },
    ];
    let woStatusExecution = '';

    for (const item of imports) {
      await page.goto('/imports/new');
      await page.getByLabel(/fonte|source/i).selectOption(item.source);
      const fileInput = page.locator('#import-file');
      await expect(fileInput).toHaveAttribute('accept', '.xlsx');
      await fileInput.setInputFiles(item.workbook);
      await page.getByRole('button', { name: /enviar|upload/i }).click();
      await expect(page).toHaveURL(/\/imports\/[0-9a-f-]+/, { timeout: 30_000 });
      await expect(page.getByText(item.source, { exact: true })).toBeVisible();
      await expect(page.locator('.status-pill')).toContainText(/concluída com erros|completed with errors/i);
      if (item.source === 'WO Status') woStatusExecution = page.url().split('/').pop() ?? '';
    }

    await page.goto('/imports/new');
    await page.getByLabel(/fonte|source/i).selectOption('WO Status');
    await page.locator('#import-file').setInputFiles(woStatusFixture);
    await page.getByRole('button', { name: /enviar|upload/i }).click();
    await expect(page.getByRole('status')).toContainText(/arquivo já importado|file already imported/i);
    await expect(page.locator(`a[href="/imports/${woStatusExecution}"]`)).toBeVisible();
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
    await expect(page).toHaveURL(/\/pending-items(?:\?|$)/);
    const pendingRow = page.locator('a.pending-row[href^="/pending-items/"]').first();
    await expect(pendingRow).toBeVisible();
    await pendingRow.click();
    await expect(page).toHaveURL(/\/pending-items\/\d+/);
    pendingId = page.url().match(/pending-items\/(\d+)/)?.[1] ?? '';
    await page.getByLabel(/justificativa|justification/i).fill('E2E: submit for human decision.');
    await page.getByRole('button', { name: /enviar para|submit for review/i }).click();
    await expect(approvalState(page)).toContainText(/enviada|submitted/i);
    await expectAccessible(page, testInfo, 'pending-detail-desktop');
    await testInfo.attach('pending-detail-desktop', {
      body: await page.screenshot({ fullPage: true }), contentType: 'image/png',
    });
  });

  test('assigns, returns, resubmits and approves with segregation of duties', async ({ page }, testInfo) => {
    await login(page, managerEmail);
    await openPending(page);
    await expect(approvalState(page)).toContainText(/submitted/i);
    await page.getByLabel(/assignee/i).fill(managerId);
    await page.getByLabel(/justification/i).fill('E2E: assignment to authorized manager.');
    await page.getByRole('button', { name: /assign review/i }).click();
    await expect(approvalState(page)).toContainText(/in review/i);
    await page.getByLabel(/justification/i).last().fill('E2E: return for additional evidence.');
    await page.getByRole('button', { name: /return for correction/i }).click();
    await expect(approvalState(page)).toContainText(/returned/i);

    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await login(page, operatorEmail);
    await openPending(page);
    await expect(approvalState(page)).toContainText(/devolvida|returned/i);
    await page.getByLabel(/justificativa|justification/i).last().fill('E2E: additional evidence supplied.');
    const resubmitted = page.waitForResponse((response) =>
      response.url().includes('/approvals/') && response.url().endsWith('/resubmit'),
    );
    await page.getByRole('button', { name: /reenviar para|resubmit for review/i }).click();
    expect((await resubmitted).status()).toBe(200);
    await expect(approvalState(page)).toContainText(/enviada|submitted/i);

    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await login(page, managerEmail);
    await openPending(page);
    await expect(approvalState(page)).toContainText(/submitted/i);
    await page.getByLabel(/assignee/i).fill(managerId);
    await page.getByLabel(/justification/i).fill('E2E: reassignment after correction.');
    await page.getByRole('button', { name: /assign review/i }).click();
    await expect(approvalState(page)).toContainText(/in review/i);
    await page.getByLabel(/justification/i).last().fill('E2E: evidence verified and approved.');
    await page.getByLabel(/confirmo conscientemente|consciously confirm/i).check();
    const approved = page.waitForResponse((response) =>
      response.url().includes('/approvals/') && response.url().endsWith('/approve'),
    );
    await page.getByRole('button', { name: /^aprovar$|^approve$/i }).click();
    expect((await approved).status()).toBe(200);
    await expect(approvalState(page)).toContainText(/approved/i);
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
    const fileInput = page.locator('#import-file');
    await expect(fileInput).toBeEnabled();
    await fileInput.setInputFiles({ name: 'invalid.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('not an xlsx') });
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
    await expect(page).toHaveURL(/\/pending-items(?:\?|$)/);
    await expect(page.locator('.pending-results')).toBeVisible();
  });

  test('expires a persisted session and redirects without leaking the resource', async ({ page }) => {
    await login(page);
    revokeSessions(operatorEmail);
    await page.goto('/pending-items');
    await expect(page).toHaveURL(/\/login\?returnUrl=%2Fpending-items/);
    await expect(page.locator('.shell')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: /entrar|sign in/i })).toBeVisible();
    await expect(page.getByRole('alert')).toContainText(/sessão expirou|session expired/i);
  });

  test('does not render public login inside an authenticated shell', async ({ page }) => {
    await login(page);
    await page.goto('/login');

    await expect(page).toHaveURL(/\/profile$/);
    await expect(page.locator('.login-page')).toHaveCount(0);
    await expect(page.locator('.shell')).toBeVisible();
  });

  test('enforces role and organization scope', async ({ page }) => {
    const authenticatedRequest = page.waitForRequest((request) =>
      request.url().endsWith('/me') && request.headers()['authorization']?.startsWith('Bearer ') === true);
    await login(page, readerEmail);
    const profileRequest = await authenticatedRequest;
    const authorization = profileRequest.headers()['authorization'];
    expect(authorization).toBeTruthy();
    const adminApiUrl = new URL('/admin/users', profileRequest.url()).toString();
    const denied = await page.request.get(adminApiUrl, {
      headers: { Authorization: authorization! },
    });
    expect(denied.status()).toBe(403);
    expect((await denied.json()).error.code).toBe('access_denied');
    await page.goto('/admin');
    await expect(page).toHaveURL(/\/profile$/);
    await expect(page.locator('a[href="/admin"]')).toHaveCount(0);
    await expect(page.getByRole('link', { name: /new import|nova importação/i })).toHaveCount(0);
    await page.locator('a[href="/search"]').click();
    await page.getByRole('searchbox', { name: /identifier|identificador/i }).fill('SYN-WO-000001');
    await page.getByRole('button', { name: /search|buscar|pesquisar/i }).click();
    await expect(page.getByText(/nenhum resultado|no results/i)).toBeVisible();
  });

  test('completes the administrative lifecycle with scoped associations', async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    const suffix = Date.now().toString(36);
    const userName = `E2E Admin Subject ${suffix}`;
    const userEmail = `admin-subject-${suffix}@example.invalid`;
    const roleKey = `e2e-role-${suffix}`;
    const groupName = `E2E Group ${suffix}`;
    await login(page, adminEmail);
    await page.locator('a[href="/admin"]').click();
    await page.locator('a[href="/admin/users"]').first().click();
    await page.locator('a[href="/admin/users/new"]').click();
    await page.waitForLoadState('networkidle');
    await page.getByLabel(/^nome$|^name$/i).fill(userName);
    await page.getByLabel(/e-mail 1|email 1/i).fill(userEmail);
    await page.getByLabel(/motivo da ação|reason for this action/i).fill('E2E approved user onboarding');
    const userCreated = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith('/admin/users') && response.request().method() === 'POST';
    }, { timeout: 30_000 });
    await page.getByRole('button', { name: /^salvar$|^save$/i }).click();
    expect((await userCreated).status()).toBe(201);
    await expect(page).toHaveURL(/\/admin\/users\/[0-9a-f-]+/, { timeout: 15_000 });

    await page.getByRole('link', { name: /voltar aos usuários|back to users/i }).click();
    await page.getByRole('link', { name: /voltar à administração|back to administration/i }).click();
    await page.locator('a[href="/admin/roles"]').first().click();
    await page.locator('a[href="/admin/roles/new"]').click();
    await page.getByLabel(/chave do papel|role key/i).fill(roleKey);
    await page.getByLabel(/descrição|description/i).fill('E2E scoped administrative role');
    await page.getByLabel(/motivo da ação|reason for this action/i).fill('E2E approved role creation');
    await page.getByRole('button', { name: /^salvar$|^save$/i }).click();
    await page.locator('[data-section="associations"]').click();
    const rolePermissions = page.getByRole('region', { name: /permissões do papel|role permissions/i });
    await rolePermissions.locator('summary').click();
    await rolePermissions.getByLabel(/destino|target/i).selectOption({ label: 'dashboard.read' });
    await rolePermissions.getByLabel(/motivo da ação|reason for this action/i).fill('E2E approved role permission');
    await rolePermissions.getByRole('button', { name: /conceder associação|grant association/i }).click();
    await expect(rolePermissions.locator('ul').getByText('dashboard.read', { exact: true })).toBeVisible();

    await page.getByRole('link', { name: /voltar à administração|back to administration/i }).click();
    await page.getByRole('link', { name: /voltar à administração|back to administration/i }).click();
    await page.locator('a[href="/admin/groups"]').first().click();
    await page.locator('a[href="/admin/groups/new"]').click();
    await page.getByLabel(/nome do grupo|group name/i).fill(groupName);
    await page.getByLabel(/motivo da ação|reason for this action/i).fill('E2E approved group creation');
    await page.getByRole('button', { name: /^salvar$|^save$/i }).click();
    await page.locator('[data-section="associations"]').click();
    const members = page.getByRole('region', { name: /membros do grupo|group members/i });
    await members.locator('summary').click();
    await members.getByLabel(/buscar usuário|search user/i).fill(userName);
    await members.getByRole('button', { name: /^buscar$|^search$/i }).click();
    await members.getByLabel(/destino|target/i).selectOption({ label: userName });
    await members.getByLabel(/motivo da ação|reason for this action/i).fill('E2E approved membership');
    await members.getByRole('button', { name: /conceder associação|grant association/i }).click();
    await expect(members.getByRole('link', { name: userName })).toBeVisible();
    const roles = page.getByRole('region', { name: /papéis associados|assigned roles/i });
    await roles.locator('summary').click();
    await roles.getByLabel(/destino|target/i).selectOption({ label: roleKey });
    await roles.getByLabel(/escopo|scope/i).selectOption('organization');
    await roles.locator('select[name="organization"]').selectOption({ index: 1 });
    await roles.getByLabel(/motivo da ação|reason for this action/i).fill('E2E approved scoped role');
    await roles.getByRole('button', { name: /conceder associação|grant association/i }).click();
    await expect(roles.getByRole('link', { name: roleKey })).toBeVisible();

    await members.getByRole('link', { name: userName }).click();
    await page.locator('[data-section="associations"]').click();
    const effective = page.getByRole('region', { name: /permissões efetivas|effective permissions/i });
    await effective.locator('summary').click();
    await expect(effective.getByText('dashboard.read')).toBeVisible();
    await expect(effective.getByText(/via grupo|via group/i)).toBeVisible();
    await expectAccessible(page, testInfo, 'admin-detail-desktop');

    await page.locator('[data-section="details"]').click();
    const userForm = page.locator('form.admin-form');
    const userReason = userForm.locator('textarea[name="reason"]').first();
    const updatedName = `${userName} Updated`;
    await userForm.getByLabel(/^nome$|^name$/i).fill(updatedName);
    await userReason.fill('E2E approved user update');
    const userUpdated = page.waitForResponse((response) =>
      response.url().includes('/admin/users/') && response.request().method() === 'PATCH');
    await userForm.getByRole('button', { name: /^salvar$|^save$/i }).click();
    expect((await userUpdated).status()).toBe(200);
    await expect(userForm.getByLabel(/^nome$|^name$/i)).toHaveValue(updatedName);

    const changeStatus = async (action: 'block' | 'unblock' | 'deactivate' | 'reactivate', label: RegExp) => {
      await page.getByRole('button', { name: label }).first().click();
      const dialog = page.locator('.admin-lifecycle-dialog');
      await expect(dialog).toBeVisible();
      await dialog.getByLabel(/motivo da ação|reason for this action/i).fill(`E2E ${action} lifecycle`);
      const changed = page.waitForResponse((response) =>
        response.url().endsWith(`/${action}`) && response.request().method() === 'POST');
      await dialog.getByRole('button', { name: label }).click();
      expect((await changed).status()).toBe(200);
    };
    await changeStatus('block', /bloquear|block/i);
    await expect(page.getByText(/bloqueado|blocked/i).first()).toBeVisible();
    await changeStatus('unblock', /desbloquear|unblock/i);
    await expect(page.getByText(/ativo|active/i).first()).toBeVisible();
    await changeStatus('deactivate', /desativar|deactivate/i);
    await expect(page.getByText(/inativo|inactive/i).first()).toBeVisible();
    await changeStatus('reactivate', /reativar|reactivate/i);
    await expect(page.getByText(/ativo|active/i).first()).toBeVisible();

    await page.locator('[data-section="associations"]').click();
    const userGroups = page.getByRole('region', { name: /grupos do usuário|user groups/i });
    await userGroups.locator('summary').click();
    await userGroups.getByRole('button', { name: /revogar|revoke/i }).click();
    const revokeDialog = page.locator('.admin-lifecycle-dialog');
    await expect(revokeDialog).toBeVisible();
    await revokeDialog.getByLabel(/motivo da ação|reason for this action/i).fill('E2E membership removal');
    await revokeDialog.getByRole('button', { name: /revogar|revoke/i }).click();
    await expect(effective.getByText('dashboard.read')).toHaveCount(0);
    const audit = execFileSync(
      process.env.E2E_PYTHON ?? 'python',
      ['../scripts/bootstrap_web_e2e.py', '--assert-admin-audit', userEmail],
      { cwd: process.cwd(), env: process.env },
    ).toString();
    expect(audit).toContain('Administrative audit verified: 12 ordered mutations.');
    await testInfo.attach('administrative-audit-summary', {
      body: Buffer.from(audit), contentType: 'text/plain',
    });
    await testInfo.attach('admin-lifecycle-desktop', {
      body: await page.screenshot({ fullPage: true }), contentType: 'image/png',
    });
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

  test('governs notification templates without changing historical occurrences', async ({ page }, testInfo) => {
    test.setTimeout(60_000);
    const suffix = Date.now().toString(36);
    const firstTitle = `E2E conclusão ${suffix}`;
    const secondTitle = `E2E conclusão revisada ${suffix}`;
    await login(page, adminEmail);
    await page.goto('/admin/notification-templates/new');
    await page.getByLabel(/tipo de evento|event type/i).selectOption('execution.completed');
    await page.getByLabel(/título|heading/i).fill(firstTitle);
    await page.getByLabel(/corpo em texto simples|plain text body/i).fill('Execução {execution_id} concluída pelo E2E.');
    await page.getByLabel(/motivo da alteração|reason for change/i).fill('E2E initial notification template');
    await page.getByRole('button', { name: /criar rascunho|create draft/i }).click();
    await expect(page).toHaveURL(/\/admin\/notification-templates\/[0-9a-f-]+/);
    const firstRevisionUrl = page.url();
    await page.getByRole('button', { name: /pré-visualizar|preview/i }).click();
    await expect(page.getByText('Execução EXEC-SYNTHETIC-001 concluída pelo E2E.')).toBeVisible();
    await page.getByRole('button', { name: /publicar versão|publish version/i }).click();
    const firstPublishDialog = page.locator('.admin-lifecycle-dialog');
    await expect(firstPublishDialog).toBeVisible();
    await firstPublishDialog.getByLabel(/motivo da alteração|reason for change/i).fill('E2E approved publication');
    await firstPublishDialog.getByRole('button', { name: /publicar versão|publish version/i }).click();
    await expect(page.getByText(/publicada e ativa|published and active/i)).toBeVisible();
    await expectAccessible(page, testInfo, 'notification-template-admin');
    await testInfo.attach('notification-template-published-desktop', {
      body: await page.screenshot({ fullPage: true }), contentType: 'image/png',
    });

    const execution = execFileSync(
      process.env.E2E_PYTHON ?? 'python',
      ['../scripts/bootstrap_web_e2e.py', '--emit-execution-notification'],
      { cwd: process.cwd(), env: process.env },
    ).toString().trim();
    expect(execution).toMatch(/^exec-template-e2e-/);
    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await login(page, operatorEmail);
    await page.goto('/notifications');
    await expect(page.getByText(firstTitle)).toBeVisible();

    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await login(page, adminEmail);
    await page.goto('/admin/notification-templates/new');
    await page.getByLabel(/tipo de evento|event type/i).selectOption('execution.completed');
    await page.getByLabel(/título|heading/i).fill('<script>alert(1)</script>');
    await page.getByLabel(/corpo em texto simples|plain text body/i).fill('Execução {execution_id}.');
    await page.getByLabel(/motivo da alteração|reason for change/i).fill('E2E malicious content rejection');
    await page.getByRole('button', { name: /criar rascunho|create draft/i }).click();
    await expect(page.getByRole('alert')).toContainText(/não permitidos|not allowed/i);

    await page.getByLabel(/título|heading/i).fill(secondTitle);
    await page.getByLabel(/corpo em texto simples|plain text body/i).fill('Nova mensagem para {execution_id}.');
    await page.getByLabel(/motivo da alteração|reason for change/i).fill('E2E replacement draft');
    await page.getByRole('button', { name: /criar rascunho|create draft/i }).click();
    await expect(page).toHaveURL(/\/admin\/notification-templates\/[0-9a-f-]+/);
    const secondRevisionUrl = page.url();
    await page.getByRole('button', { name: /publicar versão|publish version/i }).click();
    const secondPublishDialog = page.locator('.admin-lifecycle-dialog');
    await expect(secondPublishDialog).toBeVisible();
    await secondPublishDialog.getByLabel(/motivo da alteração|reason for change/i).fill('E2E replacement publication');
    await secondPublishDialog.getByRole('button', { name: /publicar versão|publish version/i }).click();
    await expect(page.getByText(/publicada e ativa|published and active/i)).toBeVisible();
    await page.goto(firstRevisionUrl);
    const firstRevisionConfiguration = page.getByRole('region', { name: /configuração|configuration/i });
    await expect(firstRevisionConfiguration.getByText(/publicada e inativa|published and inactive/i)).toBeVisible();
    await expect(page.getByLabel(/título|heading/i)).toHaveValue(firstTitle);
    await expect(page.getByLabel(/título|heading/i)).toHaveAttribute('readonly', '');

    await page.goto(secondRevisionUrl);
    await page.getByRole('button', { name: /desativar versão|deactivate version/i }).click();
    const deactivateDialog = page.locator('.admin-lifecycle-dialog');
    await expect(deactivateDialog).toBeVisible();
    await deactivateDialog.getByLabel(/motivo da alteração|reason for change/i).fill('E2E approved deactivation');
    await deactivateDialog.getByRole('button', { name: /desativar versão|deactivate version/i }).click();
    await expect(page.getByText(/publicada e inativa|published and inactive/i).first()).toBeVisible();
  });
});
