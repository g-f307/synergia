import { defineConfig } from '@playwright/test';
import base from './playwright.config';

const servers=Array.isArray(base.webServer)?base.webServer:[base.webServer!];
export default defineConfig({
  ...base,testMatch:'indicator-coverage*.spec.ts',testIgnore:[],
  // This campaign requires its own disposable database and isolated ports.
  webServer:servers.map(server=>({...server,reuseExistingServer:false})),
  outputDir:'reports/e2e-indicator-coverage-results',
  reporter:[['line'],['json',{outputFile:'reports/e2e-indicator-coverage-results/summary.json'}]],
});
