import { defineConfig, devices } from '@playwright/test';

const databaseUrl = process.env.DATABASE_URL ??
  'postgresql://synergia:synergia-local-only@127.0.0.1:5432/synergia_e2e';
const browserChannel = process.env.E2E_BROWSER_CHANNEL;
const recordVideo = process.env.E2E_RECORD_VIDEO !== 'false';
const webPort = process.env.E2E_WEB_PORT ?? '4200';
const webOrigin = `http://127.0.0.1:${webPort}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['line'], ['html', { outputFolder: 'reports/e2e-html', open: 'never' }]],
  outputDir: 'reports/e2e-results',
  use: {
    baseURL: webOrigin,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: recordVideo ? 'on' : 'off',
  },
  webServer: [
    {
      command: process.env.E2E_API_COMMAND ??
        'python -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
      cwd: '../backend',
      url: 'http://127.0.0.1:8000/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        DATABASE_URL: databaseUrl,
        SYNERGIA_ENV: 'test',
        SYNERGIA_LOCAL_AUTH_ENABLED: 'true',
        AUTH_JWT_SIGNING_KEY: 'synthetic-e2e-signing-key-at-least-32-bytes',
        AUTH_JWT_ISSUER: 'synergia-e2e',
        AUTH_JWT_AUDIENCE: 'synergia-web-e2e',
        AUTH_REFRESH_COOKIE_SECURE: 'false',
        AUTH_ALLOWED_ORIGINS: webOrigin,
        // This serial journey creates fresh sessions repeatedly to isolate its
        // scenarios. Dedicated backend tests still exercise the real limit.
        RATE_LIMIT_LOGIN_LIMIT: '1000',
        IMPORT_STORAGE_DIR: '../.test-tmp/e2e-imports',
      },
    },
    {
      command: `npm run build && python ../scripts/serve_secure_web.py --directory dist/synergia-web/browser --host 127.0.0.1 --port ${webPort}`,
      url: webOrigin,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        SYNERGIA_API_ORIGIN: 'http://127.0.0.1:8000',
      },
    },
  ],
  projects: [{
    name: 'chromium',
    use: {
      ...devices['Desktop Chrome'],
      ...(browserChannel ? { channel: browserChannel } : {}),
    },
  }],
});
