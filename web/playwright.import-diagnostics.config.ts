import { defineConfig } from '@playwright/test';

import base from './playwright.config';

// Frontend checkpoint: HTTP contracts are synthetic. The default configuration
// still runs the integrated backend journeys; no operational database is used here.
export default defineConfig({
  ...base,
  testMatch: 'import-diagnostics.spec.ts',
  webServer: Array.isArray(base.webServer) ? base.webServer.slice(1) : base.webServer,
});
