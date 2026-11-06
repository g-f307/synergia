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
  const catalogResponse = page.waitForResponse(r => r.url().endsWith('/ai/quality/scenarios'));
  await page.getByRole('link', { name: 'IA — Qualidade', exact: true }).click();
  const catalog = await (await catalogResponse).json();
  const modelAvailable = catalog.model_status === 'available';
  await expect(page).toHaveURL(/\/ai\/quality$/);
  await expect(page.locator('.shell')).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(2);
  await expect(page.locator('.waiting')).toBeVisible();
  const generate = page.getByRole('button', { name: 'Gerar explicação', exact: true });
  const explain = async () => {
    const pending = page.waitForResponse(r => r.url().endsWith('/explanations') && r.request().method() === 'POST', { timeout: 40_000 });
    await generate.click();
    const result = await pending;
    expect(result.ok()).toBeTruthy();
    const body = await result.json();
    const group = body.groups[0];
    await expect(page.locator('.explanation .source-label')).toHaveText(group.origin === 'model' ? 'Texto redigido pelo modelo' : 'Texto determinístico');
    if (group.origin === 'deterministic') {
      expect(group.state).toBe('fallback_deterministic');
      expect(group.rejection_code).toBeTruthy();
      await expect(page.locator('.explanation .rejection')).toBeVisible();
    } else {
      expect(group.rejection_code).toBeUndefined();
    }
  };
  if (modelAvailable) {
    await explain();
    await expect(page.locator('.explanation syn-badge')).toContainText(/Explicação aceita|Fallback determinístico/);
  } else {
    expect(['disabled', 'unavailable']).toContain(catalog.model_status);
    await expect(generate).toBeDisabled();
    await expect(page.getByText(catalog.model_status === 'disabled' ? 'Geração por modelo desabilitada neste ambiente' : 'Modelo validado indisponível neste ambiente', { exact: true })).toBeVisible();
    await page.locator('.explanation summary').click();
    await expect(page.locator('.explanation details')).toContainText(catalog.scenarios.find((s: { id: string }) => s.id === 'QE-A02').baseline[0].explanation);
  }
  await expect(page.locator('tbody tr')).toHaveCount(2);
  await page.locator('#quality-scenario').selectOption('QE-A01');
  await expect(page.getByText('Ausente — valor desconhecido', { exact: true })).toBeVisible();
  if (modelAvailable) {
    await explain();
    await expect(page.locator('.explanation syn-badge')).toContainText(/Evidência insuficiente|Fallback determinístico/);
  } else {
    await expect(generate).toBeDisabled();
    await page.locator('.explanation summary').click();
  }
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
