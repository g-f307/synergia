import { defineConfig } from '@playwright/test';

import base from './playwright.config';

const servers = Array.isArray(base.webServer) ? base.webServer : [base.webServer!];

export default defineConfig({
  ...base,
  testMatch: 'workorder-versions*.spec.ts',
  testIgnore: [],
  // A targeted campaign must never reuse an operational API on these ports.
  webServer: servers.map(server => ({ ...server, reuseExistingServer: false })),
  outputDir: 'reports/e2e-workorder-versions-results',
  reporter: [['line'], ['html', { outputFolder: 'reports/e2e-workorder-versions-html', open: 'never' }]],
});
