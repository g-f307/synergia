import { expect, test } from '@playwright/test';

const webOrigin = `http://127.0.0.1:${process.env.E2E_WEB_PORT ?? '4200'}`;
const apiOrigin = 'http://127.0.0.1:8000';

test('published build runs under its definitive CSP and security headers', async ({ page }) => {
  const policyViolations: string[] = [];
  page.on('console', (message) => {
    if (/content security policy/i.test(message.text())) {
      policyViolations.push(message.text());
    }
  });

  const response = await page.goto('/login');
  expect(response).not.toBeNull();
  const headers = response!.headers();
  expect(headers['content-security-policy']).toContain("frame-ancestors 'none'");
  expect(headers['content-security-policy']).toContain(`connect-src 'self' ${apiOrigin}`);
  expect(headers['content-security-policy']).not.toContain('unsafe-eval');
  expect(headers['x-frame-options']).toBe('DENY');
  expect(headers['x-content-type-options']).toBe('nosniff');
  await expect(page.getByRole('button', { name: /entrar|sign in/i })).toBeVisible();
  const configuredApi = await page.evaluate(() => (
    globalThis as typeof globalThis & { __SYNERGIA_CONFIG__?: { apiUrl?: string } }
  ).__SYNERGIA_CONFIG__?.apiUrl);
  expect(configuredApi).toBe(apiOrigin);
  expect(policyViolations).toEqual([]);
});

test('browser refuses to render the published application inside a frame', async ({
  browser,
}) => {
  const context = await browser.newContext();
  const parent = await context.newPage();
  await parent.setContent(`<iframe title="blocked" src="${webOrigin}/login"></iframe>`);
  const child = parent.frames().find((frame) => frame !== parent.mainFrame());
  expect(child).toBeDefined();
  await child!.waitForLoadState().catch(() => undefined);

  expect(await child!.locator('app-root').count()).toBe(0);
  await context.close();
});
