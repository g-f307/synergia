'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('../../web/node_modules/playwright');
const { openNfp, openProductionPlan } = require('./production-plan.cjs');

for (const scenario of ['folded', 'expanded', 'compact', 'iframe', 'already-open', 'same-tab', 'nested-shortcut', 'missing', 'ambiguous', 'wrong-destination']) {
test(`navegação baseada nos HTMLs: ${scenario}`, {timeout: 15000}, async () => {
  const browser = await chromium.launch({channel:'chrome', headless:true});
  const context = await browser.newContext();
  const visits = [];
  const target = scenario === 'same-tab' ? '_self' : '_blank';
  const destination = scenario === 'wrong-destination' ? 'http://other.example/' : 'http://nfp.lge.com/';
  let links = `<a href="http://wrong.example/">N-FP (N-FP)</a>`;
  const label = scenario === 'nested-shortcut'
    ? '<span>N&#8209;FP</span> <span>( GERP )</span>'
    : 'N-FP (GERP)';
  if (scenario === 'folded') {
    links += `<a class="ellipsis" href="#a" onclick="fn_mySystemMove('http://nfp.lge.com')" title="N-FP (GERP)"> N-FP (GERP) </a>`;
  } else if (scenario !== 'missing') {
    links += `<a target="${target}" href="${destination}">${label}</a>`;
  }
  if (scenario === 'ambiguous') links += `<a href="${destination}">N-FP (GERP)</a>`;
  const initial = scenario === 'already-open';
  const button = scenario === 'compact'
    ? `<a onclick="systemMapFavoriteAppLink('S')">My<br>System</a>`
    : `<div id="divMySystem"><h2>My System</h2><a class="btn_systemMap" onclick="systemMapFavoriteAppLink('B')"><span>System Map</span></a></div>`;
  const panel = scenario === 'folded'
    ? `<a href="#" class="btn_open" onclick="fnSize('small', 'button');" title="Unfold"><span>Open &amp; Close</span></a><div id="panel" hidden>${button}</div>
       <script>function fnSize(){document.querySelector('.btn_open').hidden=true;document.querySelector('#panel').hidden=false}
       function fn_mySystemMove(url){window.open(url)}</script>`
    : button;
  const menu = `${panel}<div id="systemMapLinkLayer" style="display:${initial ? 'block' : 'none'}">${initial ? links : ''}</div><script>window.menuClicks=0;function systemMapFavoriteAppLink(){window.menuClicks++;document.querySelector('#systemMapLinkLayer').style.display='block';setTimeout(()=>{document.querySelector('#systemMapLinkLayer').innerHTML=${JSON.stringify(links)}},40)}</script>`;
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    visits.push(url.hostname);
    if (url.hostname === 'newep.lge.com') return route.fulfill({contentType:'text/html', body: scenario === 'iframe' && !url.pathname.endsWith('/frame') ? '<iframe src="/portal/frame"></iframe>' : menu});
    if (url.hostname === 'nfp.lge.com') return route.fulfill({contentType:'text/html', body: `<button onclick="document.querySelector('#analysis-menu').hidden=false">Analysis</button><div id="analysis-menu" hidden><div class="q-item" role="listitem"><div>Production Plan [R+F]</div><button onclick="window.open('/#/nfp/planning/production-plan-rf?_mid=synthetic')"><i>open_in_new</i></button></div></div><script>if(location.hash){document.body.innerHTML='<h1>Production Plan [R+F]</h1><div class="q-gutter-xs"><button class="say-ico-btn" onclick="window.searched=true"><i class="material-icons">refresh</i><span class="block">Search</span></button><button class="say-ico-btn" onclick="window.downloaded=true"><i class="material-icons">download</i><span class="block">Download</span></button></div>'}</script>`});
    return route.fulfill({contentType:'text/html',body:'<p>Analysis</p>'});
  });
  try {
    const portal = await context.newPage();
    await portal.goto('http://newep.lge.com/portal/main/portalMain.do');
    // A pre-existing NFP tab must not mask a failed navigation.
    const stale = await context.newPage();
    await stale.goto('http://nfp.lge.com/');
    if (['missing', 'ambiguous', 'wrong-destination'].includes(scenario)) {
      const expectedError = {
        missing: /nenhum atalho clicável/,
        ambiguous: /Mais de um atalho/,
        'wrong-destination': /nenhuma aba chegou/,
      }[scenario];
      await assert.rejects(openNfp(context, portal, () => {}, 1000), expectedError);
    } else {
      const nfp = await openNfp(context, portal, () => {}, 3000);
      assert.notEqual(nfp, stale);
      assert.equal(new URL(nfp.url()).hostname, 'nfp.lge.com');
      if (scenario !== 'same-tab') {
        const frame = portal.frames().find(f => f.url().endsWith('/frame')) || portal.mainFrame();
        assert.equal(await frame.evaluate(() => window.menuClicks), initial ? 0 : 1);
        if (scenario === 'folded') assert.equal(await frame.locator('#panel').isVisible(), true);
      }
      const report = await openProductionPlan(context, nfp, () => {}, 3000);
      assert.equal(new URL(report.url()).hash.split('?')[0], '#/nfp/planning/production-plan-rf');
      assert.equal(await report.evaluate(() => !!window.searched || !!window.downloaded), false);
    }
    assert.equal(visits.includes('wrong.example'), false);
  } finally { await browser.close(); }
});
}
