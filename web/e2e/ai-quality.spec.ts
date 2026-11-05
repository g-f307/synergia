import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';

test.use({ video: 'off' });

test('quality AI uses the authenticated Synergia shell and read-only synthetic scenarios', async ({ page }, info) => {
  test.setTimeout(90_000);
  const email = 'operator.e2e@example.invalid';
  execFileSync(process.env.E2E_PYTHON ?? 'python', ['../scripts/bootstrap_web_e2e.py', '--revoke-email', email], { env: process.env });
  await page.goto('/login');
  await page.getByLabel(/e-mail|email/i).fill(email);
  await page.getByLabel(/senha|password/i).fill('synthetic-e2e-password-63');
  await page.getByRole('button', { name: /entrar|sign in/i }).click();
  await expect(page).toHaveURL(/\/profile/);
  await page.getByRole('link', { name: 'IA — Qualidade', exact: true }).click();
  await expect(page).toHaveURL(/\/ai\/quality$/);
  await expect(page.locator('.shell')).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(2);
  await expect(page.locator('.waiting')).toBeVisible();
  await page.getByRole('button', { name: 'Gerar explicação', exact: true }).click();
  await expect(page.locator('.explanation syn-badge')).toContainText(/Explicação aceita|Fallback determinístico/, { timeout: 40_000 });
  await expect(page.locator('tbody tr')).toHaveCount(2);
  await page.locator('#quality-scenario').selectOption('QE-A01');
  await expect(page.getByText('Ausente — valor desconhecido', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Gerar explicação', exact: true }).click();
  await expect(page.locator('.explanation syn-badge')).toContainText(/Evidência insuficiente|Fallback determinístico/, { timeout: 40_000 });
  await expect(page.locator('.explanation')).toContainText('O valor ausente não pode ser determinado.');
  for (const theme of ['light', 'dark']) {
    if (theme === 'dark') await page.getByRole('button', { name: /alternar tema/i }).click();
    const results = await new AxeBuilder({ page }).include('.quality-page').analyze();
    expect(results.violations.filter(v => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([]);
    await page.screenshot({ path: info.outputPath(`quality-${theme}.png`) });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.locator('#quality-scenario').selectOption('QD3-E01');
  await expect(page.getByText('Nenhuma ocorrência detectada', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Gerar explicação', exact: true })).toBeDisabled();
  await page.screenshot({ path: info.outputPath('quality-mobile.png') });
});
