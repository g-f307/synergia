'use strict';

// Local discovery harness only. No credentials, traces or session state saved.
const { chromium } = require('../../web/node_modules/playwright');
const readline = require('node:readline');

(async () => {
  process.umask(0o077);
  const browser = await chromium.launch({ channel: 'chrome', headless: false });
  const context = await browser.newContext({ viewport: null, acceptDownloads: false });
  const page = await context.newPage();
  browser.on('disconnected', () => process.exit(0));
  try {
    await page.goto('http://newep.lge.com/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    console.log('Janela aberta. Aguardando login manual; nenhuma coleta iniciada.');
  } catch {
    console.log('Janela aberta; navegação inicial não concluída. Verifique a conectividade na janela.');
  }
  const input = readline.createInterface({ input: process.stdin });
  for await (const line of input) {
    if (line.trim() === 'status') {
      console.log(JSON.stringify({ pages: context.pages().map((p, index) => {
        try { return { index, origin: new URL(p.url()).origin }; }
        catch { return { index, origin: 'unknown' }; }
      }) }));
    } else if (line.trim() === 'close') {
      await browser.close();
      break;
    }
  }
})().catch(() => {
  console.error('Não foi possível iniciar a janela de descoberta.');
  process.exitCode = 1;
});
