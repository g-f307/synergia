import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

const operatorEmail = 'operator.e2e@example.invalid';
const password = process.env.E2E_PASSWORD ?? 'synthetic-e2e-password-63';
const fixture = path.resolve('../data/synthetic/fixtures/minimal-comprehensive/n-fp.xlsx');

function revokeSessions(): void {
  execFileSync(process.env.E2E_PYTHON ?? 'python', [
    '../scripts/bootstrap_web_e2e.py',
    '--revoke-email',
    operatorEmail,
  ], { cwd: process.cwd(), env: process.env });
}

async function login(page: import('@playwright/test').Page): Promise<void> {
  revokeSessions();
  await page.goto('/login');
  await page.getByLabel(/e-mail|email/i).fill(operatorEmail);
  await page.getByLabel(/senha|password/i).fill(password);
  await page.getByRole('button', { name: /entrar|sign in/i }).click();
  await expect(page).toHaveURL(/\/profile/);
}

test('opens a scoped, responsive and accessible TV monitor', async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await login(page);

  await page.goto('/imports/new');
  await page.locator('#import-file').setInputFiles(fixture);
  await page.getByRole('button', { name: /enviar|upload/i }).click();
  const existingImport = page.getByRole('link', { name: /ver resultado da importação|view import result/i });
  await expect.poll(async () => /\/imports\/[0-9a-f-]+/.test(page.url()) || await existingImport.isVisible()).toBe(true);
  let expectsImportedExecution = true;
  if (await existingImport.isVisible()) {
    expectsImportedExecution = false;
    await existingImport.click();
  }
  await expect(page).toHaveURL(/\/imports\/[0-9a-f-]+/, { timeout: 30_000 });
  const executionId = page.url().split('/').pop() ?? '';

  await page.route(/\/executions\?.*/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        generated_at: '2026-10-27T03:00:00Z',
        items: [
          {
            execution_id: executionId || 'e2e-active-execution',
            organization_id: 'org-synthetic',
            status: 'validating',
            lifecycle: 'active',
            attempt: 1,
            source: 'N-FP',
            file_types: ['xlsx'],
            file_count: 1,
            rows_read: 4,
            error_count: 0,
            warning_count: 0,
            started_at: '2026-10-27T02:59:00Z',
            finished_at: null
          }
        ],
        pagination: { page: 1, page_size: 25, total: 1, pages: 1 },
        sort: 'newest'
      })
    });
  });

  await page.getByRole('link', { name: /abrir modo tv|open tv mode/i }).click();
  await expect(page).toHaveURL(/\/tv$/);
  await expect(page.locator('.shell')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: /monitor de execuções|execution monitor/i })).toBeVisible();
  await expect.poll(() => page.locator('.tv-brand img').evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  await page.locator('.tv-brand img').evaluate((image: HTMLImageElement) => image.decode());
  await page.evaluate(() => document.fonts.ready);
  if (expectsImportedExecution) await expect(page.getByText(executionId)).toBeVisible();
  else await expect(page.locator('.tv-execution-table tbody tr').first()).toBeVisible();
  await expect(page.getByRole('button', { name: /sair do modo tv|exit tv mode/i })).toBeVisible();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? ''))).toEqual([]);
  await testInfo.attach('tv-mode-desktop', {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });

  await page.getByRole('button', { name: /atividade por fonte|activity by source/i }).click();
  await expect(page.getByRole('heading', { name: /atividade recente por fonte|recent activity by source/i })).toBeVisible();
  await expect(page.locator('.tv-volume-bar').first()).toBeVisible();
  await expect(page.locator('.tv-attention-ring').first()).toBeVisible();
  const sourcesAccessibility = await new AxeBuilder({ page }).analyze();
  expect(sourcesAccessibility.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? ''))).toEqual([]);
  await testInfo.attach('tv-mode-sources', {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });

  await page.getByRole('button', { name: /alternar tema|toggle theme/i }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  const darkAccessibility = await new AxeBuilder({ page }).analyze();
  expect(darkAccessibility.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? ''))).toEqual([]);
  for (const buttonName of [/tela cheia|full screen/i, /sair do modo tv|exit tv mode/i]) {
    await page.getByRole('button', { name: buttonName }).hover();
    const hoverAccessibility = await new AxeBuilder({ page }).analyze();
    expect(hoverAccessibility.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? ''))).toEqual([]);
  }
  await testInfo.attach('tv-mode-dark', {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });

  await page.getByRole('button', { name: /execuções recentes|recent executions/i }).click();
  await expect(page.locator('.tv-status[data-state="active"]').first()).toBeVisible();
  const executionsDarkAccessibility = await new AxeBuilder({ page }).analyze();
  expect(executionsDarkAccessibility.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? ''))).toEqual([]);
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(page.locator('.tv-monitor')).toBeVisible();
  if (expectsImportedExecution) await expect(page.getByText(executionId)).toBeVisible();
  else await expect(page.locator('.tv-execution-table tbody tr').first()).toBeVisible();
  await testInfo.attach('tv-mode-compact', {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });

  await page.getByRole('button', { name: /atividade por fonte|activity by source/i }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.tv-source-card').first()).toBeVisible();
  expect(await page.locator('.tv-monitor').evaluate((monitor) => monitor.scrollWidth <= monitor.clientWidth)).toBe(true);
  expect(await page.locator('.tv-source-card').first().evaluate((card) => card.getBoundingClientRect().width <= 366)).toBe(true);
  const mobileSourcesAccessibility = await new AxeBuilder({ page }).analyze();
  expect(mobileSourcesAccessibility.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? ''))).toEqual([]);

  await page.getByRole('button', { name: /sair do modo tv|exit tv mode/i }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.locator('.shell')).toBeVisible();
});
