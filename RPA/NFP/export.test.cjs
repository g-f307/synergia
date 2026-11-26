'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require('../../web/node_modules/playwright');
const { exportProductionPlan } = require('./production-plan.cjs');

test('NW4 só é exportada depois de uma busca confirmada', { timeout: 15000 }, async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'nfp-export-'));
  try {
    const context = await browser.newContext({ acceptDownloads: true });
    await context.route('**/*', route => route.fulfill({
      contentType: 'text/html',
      body: `
        <div><span>Plant</span><div class="q-field__native">
          <input class="q-field__input" type="search" role="combobox" id="plant" value="NW1" aria-expanded="false" aria-controls="plant-options">
        </div></div>
        <div id="plant-options" hidden>
          <div id="nw4-option" hidden><span>NW4</span></div>
          <div><span>NW40</span></div>
        </div>
        <input id="date" value="2026-11-01">
        <button onclick="window.wrongButton=true">Search</button>
        <div class="q-gutter-xs">
          <button id="download" class="q-btn say-ico-btn" type="button"><span class="q-btn__content"><i class="material-icons" aria-hidden="true">download</i><span class="block">Download</span></span></button>
          <button id="search" class="q-btn say-ico-btn" type="button" disabled><span class="q-btn__content"><i class="material-icons" aria-hidden="true">refresh</i><span class="block">Search</span></span></button>
        </div>
        <p id="loading" hidden>Loading, please wait...</p>
        <table><tr><td>NW4</td><td>Previous results</td></tr></table>
        <script>
          window.clicks = 0;
          window.finished = false;
          const menu = document.getElementById('plant-options');
          const option = document.getElementById('nw4-option');
          plant.onclick = () => {
            menu.hidden = false;
            plant.setAttribute('aria-expanded', 'true');
            option.hidden = true;
          };
          plant.oninput = () => { option.hidden = plant.value !== 'NW4'; };
          option.onclick = () => {
            menu.hidden = true;
            plant.setAttribute('aria-expanded', 'false');
            plant.value = 'NW4';
            window.selectedPlant = 'NW4';
            document.getElementById('search').disabled = false;
          };
          download.onclick = () => {
            window.clicks++;
            const link = document.createElement('a');
            link.href = 'data:application/octet-stream,' + (window.finished ? 'new-results' : 'stale-results');
            link.download = 'Production_Plan_NW4.xlsx';
            link.click();
          };
        </script>`,
    }));
    const report = await context.newPage();
    await report.goto('http://nfp.lge.com/#/nfp/planning/production-plan-rf');
    await assert.rejects(exportProductionPlan(report, directory, 'NW4', () => {}, 700), /conclusão da busca da NW4/);
    assert.equal(await report.evaluate(() => window.clicks), 0);
    await report.evaluate(() => {
      document.getElementById('search').onclick = () => {
        const loading = document.getElementById('loading');
        loading.hidden = false;
        setTimeout(() => {
          window.finished = window.selectedPlant === 'NW4'
            && document.getElementById('date').value === '2026-11-01';
          loading.hidden = true;
        }, 500);
      };
    });
    const file = await exportProductionPlan(report, directory, 'NW4', () => {}, 3000);
    assert.equal(path.basename(file), 'Production_Plan_NW4.xlsx');
    assert.equal(fs.readFileSync(file, 'utf8'), 'new-results');
    assert.equal(await report.evaluate(() => window.clicks), 1);
    assert.equal(await report.evaluate(() => Boolean(window.wrongButton)), false);
  } finally {
    await browser.close();
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
