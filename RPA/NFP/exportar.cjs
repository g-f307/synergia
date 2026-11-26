'use strict';

const path = require('node:path');
const { chromium } = require('../../web/node_modules/playwright');
const { portalReady, openNfp, openProductionPlan, exportProductionPlan, FlowError, waitFor } = require('./production-plan.cjs');

async function main(args) {
  const match = /^--nwm?(\d+)$/.exec(args[0] || '--nwm1');
  if (!match || args.length > 1) throw new FlowError('Uso: node RPA/NFP/exportar.cjs [--nwm4]');
  const plant = 'NW' + match[1];
  process.umask(0o077);
  const browser = await chromium.launch({ channel: 'chrome', headless: false });
  try {
    const context = await browser.newContext({ viewport: null, acceptDownloads: true });
    const page = await context.newPage();
    // Portal redirects can finish in the original tab or in a popup.
    console.log('Conclua a autenticação no navegador para abrir o portal.');
    await page.goto('http://newep.lge.com/', { waitUntil: 'domcontentloaded' });
    const authenticated = await waitFor(() => context.pages().find(portalReady), 300000);
    const nfp = await openNfp(context, authenticated);
    const report = await openProductionPlan(context, nfp);
    await exportProductionPlan(report, path.join(__dirname, 'downloads'), plant);
  } finally {
    await browser.close();
  }
}

main(process.argv.slice(2)).catch(error => {
  console.error(error instanceof FlowError ? error.message : 'Falha na etapa indicada. Confira o acesso ao portal e ao Chrome.');
  process.exitCode = 1;
});
