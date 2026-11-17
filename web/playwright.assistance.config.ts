import { defineConfig } from '@playwright/test';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import base from './playwright.config';

const apiPort = process.env.E2E_AI_API_PORT ?? '8001';
const webPort = process.env.E2E_AI_WEB_PORT ?? '4201';
const counterFile =
  process.env.E2E_PROVIDER_COUNTER_FILE ??
  join(mkdtempSync(join(tmpdir(), 'synergia-e2e-counter-')), 'counter.json');
process.env.E2E_PROVIDER_COUNTER_FILE = counterFile;
const webOrigin = `http://127.0.0.1:${webPort}`;
const servers = Array.isArray(base.webServer) ? base.webServer : [base.webServer!];

export default defineConfig({
  ...base,
  testMatch: 'assistance.spec.ts',
  testIgnore: [],
  outputDir: 'reports/e2e-assistance-results',
  reporter: [['line'], ['html', { outputFolder: 'reports/e2e-assistance-html', open: 'never' }]],
  use: { ...base.use, baseURL: webOrigin, video: 'on' },
  webServer: [
    {
      ...servers[0],
      command: `${process.env.E2E_PYTHON ?? 'python'} ../scripts/serve_assistance_e2e.py`,
      url: `http://127.0.0.1:${apiPort}/health`,
      reuseExistingServer: false,
      env: {
        ...servers[0].env,
        E2E_API_PORT: apiPort,
        E2E_PROVIDER_COUNTER_FILE: counterFile,
        AUTH_ALLOWED_ORIGINS: webOrigin,
        SYNERGIA_AI_ASSISTANCE_ENABLED: 'true',
        SYNERGIA_AI_ASSISTANCE_ENDPOINT: 'http://127.0.0.1:11434',
        SYNERGIA_AI_ASSISTANCE_MODEL: 'controlled-e2e',
        SYNERGIA_AI_ASSISTANCE_DIGEST: 'sha256:' + '1'.repeat(64),
      },
    },
    {
      ...servers[1],
      command: `npm run build && ${process.env.E2E_PYTHON ?? 'python'} ../scripts/serve_secure_web.py --directory dist/synergia-web/browser --host 127.0.0.1 --port ${webPort}`,
      url: webOrigin,
      reuseExistingServer: false,
      env: { ...servers[1].env, SYNERGIA_API_ORIGIN: `http://127.0.0.1:${apiPort}` },
    },
  ],
});
