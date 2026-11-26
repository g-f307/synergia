'use strict';
const fs = require('node:fs');
const path = require('node:path');
const ALLOWED = new Set(['http://newep.lge.com', 'https://newep.lge.com', 'http://nfp.lge.com', 'https://nfp.lge.com']);

class FlowError extends Error {}
class WaitTimeout extends FlowError {}
function allowed(url) {
  try { return ALLOWED.has(new URL(url).origin); } catch { return false; }
}
function portalReady(page) {
  try {
    const url = new URL(page.url());
    return ['http://newep.lge.com', 'https://newep.lge.com'].includes(url.origin)
      && url.pathname.startsWith('/portal/') && !/login|ssoagent/i.test(url.pathname);
  } catch { return false; }
}
async function waitFor(find, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const result = await find();
    if (result) return result;
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new WaitTimeout('Etapa não concluída no prazo; nenhuma repetição automática de login.');
}
function portalFrame(frame) {
  try { return ['http://newep.lge.com', 'https://newep.lge.com'].includes(new URL(frame.url()).origin); }
  catch { return false; }
}

const NFP_GERP_LABEL = /^N\s*[-‐‑–]?\s*FP\s*\(\s*GERP\s*\)$/i;
const UNFOLD = 'a.btn_open[title="Unfold"][onclick*="fnSize(\'small\', \'button\')"]';
const SYSTEM_MAP = 'a.btn_systemMap[onclick*="systemMapFavoriteAppLink(\'B\')"]';
const COMPACT_SYSTEM_MAP = 'a[onclick*="systemMapFavoriteAppLink(\'S\')"]';
const NFP_SHORTCUT = 'a.ellipsis[title="N-FP (GERP)"][onclick*="fn_mySystemMove(\'http://nfp.lge.com\')"]';

async function visibleItems(locator) {
  const items = [];
  for (let i = 0; i < await locator.count(); i++) {
    if (await locator.nth(i).isVisible().catch(() => false)) items.push(locator.nth(i));
  }
  return items;
}

async function nfpLink(portal) {
  const matches = [];
  for (const frame of portal.frames()) {
    if (!portalFrame(frame)) continue;
    const layer = frame.locator('#systemMapLinkLayer');
    // The portal loads its list asynchronously into this exact container.
    const scope = await layer.count() ? layer : frame;
    const exact = await visibleItems(scope.locator(NFP_SHORTCUT));
    if (exact.length) {
      matches.push(...exact);
      continue;
    }
    const shortcuts = scope.locator('a, button, [role="link"], [role="button"]');
    const visible = await visibleItems(shortcuts.filter({ hasText: NFP_GERP_LABEL }));
    if (visible.length) matches.push(...visible);
    else matches.push(...await visibleItems(scope.locator('[onclick]').filter({ hasText: NFP_GERP_LABEL })));
  }
  if (matches.length > 1) throw new FlowError('Mais de um atalho N-FP (GERP) visível; navegação interrompida.');
  return matches[0] || null;
}

async function portalControl(portal, selector, description) {
  const controls = [];
  for (const frame of portal.frames()) {
    if (!portalFrame(frame)) continue;
    controls.push(...await visibleItems(frame.locator(selector)));
  }
  if (controls.length > 1) throw new FlowError(`Mais de um controle visível para ${description}.`);
  return controls[0] || null;
}

function unfoldControl(portal) {
  return portalControl(portal, UNFOLD, 'expandir o painel');
}

async function mySystemControl(portal) {
  return await portalControl(portal, SYSTEM_MAP, 'System Map')
    || await portalControl(portal, COMPACT_SYSTEM_MAP, 'My System compacto');
}

async function openNfp(context, portal, notify = console.log, timeout = 30000) {
  if (!portalReady(portal)) throw new FlowError('Portal autenticado não confirmado.');
  await portal.bringToFront();
  let link = await nfpLink(portal);
  if (!link) {
    let alreadyOpen = false;
    for (const frame of portal.frames()) {
      if (portalFrame(frame) && await frame.locator('#systemMapLinkLayer').isVisible().catch(() => false)) alreadyOpen = true;
    }
    if (!alreadyOpen) {
      const entry = await waitFor(async () => {
        const systemMap = await portalControl(portal, SYSTEM_MAP, 'System Map');
        if (systemMap) return { systemMap };
        const unfold = await unfoldControl(portal);
        if (unfold) return { unfold };
        const compact = await portalControl(portal, COMPACT_SYSTEM_MAP, 'My System compacto');
        return compact ? { systemMap: compact } : null;
      }, timeout);
      if (entry.unfold) {
        notify('Expandindo o painel lateral pelo botão Unfold.');
        await entry.unfold.click({ timeout });
        entry.systemMap = await waitFor(() => portalControl(portal, SYSTEM_MAP, 'System Map'), timeout);
      }
      notify('Abrindo My System pelo controle System Map.');
      await entry.systemMap.click({ noWaitAfter: true, timeout });
    }
    link = await waitFor(() => nfpLink(portal), timeout).catch(error => {
      if (error instanceof WaitTimeout) {
        throw new FlowError('My System abriu, mas nenhum atalho clicável N-FP (GERP) foi encontrado.');
      }
      throw error;
    });
  }
  notify('Selecionando exclusivamente N-FP (GERP).');
  const before = new Set(context.pages());
  const navigated = new Set();
  const listeners = new Map();
  for (const page of before) {
    const listener = frame => { if (frame === page.mainFrame()) navigated.add(page); };
    listeners.set(page, listener);
    page.on('framenavigated', listener);
  }
  let nfp;
  try {
    try {
      await link.click({ noWaitAfter: true, timeout });
    } catch (error) {
      if (error.name !== 'TimeoutError') throw error;
      throw new FlowError('O atalho N-FP (GERP) foi encontrado, mas o navegador não conseguiu clicar nele.');
    }
    notify('Clique em N-FP (GERP) concluído. Aguardando a aba do NFP.');
    nfp = await waitFor(async () => {
      for (const page of context.pages()) {
        if (before.has(page) && !navigated.has(page)) continue;
        if (!allowed(page.url()) || new URL(page.url()).hostname !== 'nfp.lge.com') continue;
        return page;
      }
      return null;
    }, timeout).catch(error => {
      if (error instanceof WaitTimeout) {
        throw new FlowError('O clique foi concluído, mas nenhuma aba chegou ao endereço do NFP.');
      }
      throw error;
    });
  } finally {
    for (const [page, listener] of listeners) page.removeListener('framenavigated', listener);
  }
  await nfp.bringToFront();
  notify('NFP aberto pela opção GERP. Consulta/exportação ainda não iniciadas.');
  return nfp;
}

function productionPlanPage(page) {
  if (!allowed(page.url())) return false;
  const url = new URL(page.url());
  return url.hostname === 'nfp.lge.com' && url.hash.split('?')[0] === '#/nfp/planning/production-plan-rf';
}

function reportAction(page, label, icon) {
  return page.locator('.q-gutter-xs button.say-ico-btn').filter({
    has: page.locator('span.block').filter({ hasText: new RegExp(`^\\s*${label}\\s*$`) }),
  }).filter({
    has: page.locator('i.material-icons').filter({ hasText: new RegExp(`^\\s*${icon}\\s*$`) }),
  });
}

async function openProductionPlan(context, nfp, notify = console.log, timeout = 30000) {
  if (!allowed(nfp.url()) || new URL(nfp.url()).hostname !== 'nfp.lge.com') throw new FlowError('Origem NFP não confirmada.');
  const analysis = await waitFor(async () => {
    const items = await visibleItems(nfp.getByText('Analysis', { exact: true }));
    if (items.length > 1) throw new FlowError('Menu Analysis ambíguo.');
    return items.length ? items : null;
  }, timeout).catch(error => {
    if (error instanceof WaitTimeout) {
      throw new FlowError('O NFP abriu, mas o menu Analysis não apareceu.');
    }
    throw error;
  });
  notify('Abrindo Analysis → Production Plan [R+F].');
  await analysis[0].hover();
  const rows = nfp.locator('.q-item[role="listitem"]').filter({ has: nfp.getByText('Production Plan [R+F]', { exact: true }) });
  if (!(await visibleItems(rows)).length) await analysis[0].click();
  const row = await waitFor(async () => {
    const items = await visibleItems(rows);
    if (items.length > 1) throw new FlowError('Item Production Plan ambíguo.');
    return items[0] || null;
  }, timeout);
  // botao.html: open_in_new button inside the specific Quasar list item.
  const buttons = await visibleItems(row.getByRole('button').filter({ has: nfp.locator('i').filter({ hasText: /^open_in_new$/ }) }));
  if (buttons.length !== 1) throw new FlowError('Botão de abertura do Production Plan ausente ou ambíguo.');
  const before = new Set(context.pages());
  await buttons[0].click({ noWaitAfter: true });
  const report = await waitFor(async () => {
    for (const page of context.pages()) {
      if (before.has(page) && page !== nfp) continue;
      if (!productionPlanPage(page)) continue;
      if (await page.getByText('Production Plan [R+F]', { exact: true }).first().isVisible().catch(() => false)
        && await reportAction(page, 'Search', 'refresh').isVisible().catch(() => false)) return page;
    }
    return null;
  }, timeout);
  await report.bringToFront();
  notify('Tela Production Plan [R+F] aberta.');
  return report;
}

async function plantControl(report) {
  const labelled = await visibleItems(report.getByLabel('Plant', { exact: true }).and(
    report.locator('select, input, [role="combobox"], button, .q-select')
  ));
  if (labelled.length === 1) return labelled[0];
  if (labelled.length > 1) throw new FlowError('Filtro Plant ambíguo.');

  // Some versions render Plant as plain text next to the dropdown.
  const controls = [];
  for (const label of await visibleItems(report.getByText('Plant', { exact: true }))) {
    const group = label.locator('xpath=ancestor::*[descendant::select or descendant::*[@role="combobox"] or descendant::*[contains(concat(" ", normalize-space(@class), " "), " q-select ")]][1]');
    const items = await visibleItems(group.locator('select, [role="combobox"], .q-select:not(:has([role="combobox"]))'));
    if (items.length === 1) controls.push(items[0]);
  }
  if (controls.length > 1) throw new FlowError('Filtro Plant ambíguo.');
  return controls[0] || null;
}

async function unlabelledPlantOptions(report, plantCode) {
  const matches = await visibleItems(report.getByText(plantCode, { exact: true }));
  const options = [];
  for (const match of matches) {
    const inPlantList = await match.evaluate(el => {
      if (el.closest('table, [role="grid"], [role="row"], [role="cell"], [role="gridcell"]')) return false;
      // Custom dropdowns may render plain sibling items instead of ARIA options.
      for (let item = el; item?.parentElement; item = item.parentElement) {
        if (!/^NW[A-Z0-9]+$/.test(item.innerText?.trim() || '')) return false;
        const codes = [...item.parentElement.children]
          .filter(sibling => sibling.getClientRects().length && getComputedStyle(sibling).visibility === 'visible')
          .map(sibling => sibling.innerText?.trim())
          .filter(text => /^NW[A-Z0-9]+$/.test(text || ''));
        if (new Set(codes).size >= 3) return true;
      }
      return false;
    });
    if (inPlantList) options.push(match);
  }
  return options;
}

async function exportProductionPlan(report, directory, plantCode, notify = console.log, timeout = 180000) {
  if (!/^NW\d+$/.test(plantCode)) throw new FlowError('Código de plant inválido.');
  if (!productionPlanPage(report)) throw new FlowError('Tela Production Plan [R+F] não confirmada.');
  const loading = report.getByText(/^Loading,\s*please wait(?:\.{1,3}|…)?$/i);
  const busy = async () => (await visibleItems(loading)).length > 0;
  const search = reportAction(report, 'Search', 'refresh');
  const downloadButton = reportAction(report, 'Download', 'download');
  if (await search.count() !== 1 || await downloadButton.count() !== 1) {
    throw new FlowError('Não encontrei um único botão Search e um único Download na barra do relatório.');
  }
  notify('Procurando o filtro Plant.');
  await waitFor(async () => !(await busy()), timeout);
  const plant = await waitFor(() => plantControl(report), 15000).catch(error => {
    if (error instanceof WaitTimeout) throw new FlowError('Não encontrei o controle do filtro Plant.');
    throw error;
  });
  const nativeSelect = await plant.evaluate(el => el.tagName === 'SELECT');
  if (nativeSelect) {
    await plant.selectOption({ label: plantCode });
  } else {
    const inputSelector = 'input.q-field__input[type="search"][role="combobox"]';
    const inputs = await visibleItems(plant.and(report.locator(inputSelector)).or(plant.locator(inputSelector)));
    if (inputs.length > 1) throw new FlowError('Campo de busca do filtro Plant ambíguo.');
    const input = inputs[0];
    const control = input || plant;
    await control.click();
    if (input && await input.isEditable()) {
      notify(`Filtrando a lista de plantas por ${plantCode}.`);
      await input.fill(plantCode);
    }
    const option = await waitFor(async () => {
      const menuId = await control.getAttribute('aria-controls') || await control.getAttribute('aria-owns');
      const linkedMenu = menuId?.trim().split(/\s+/).map(id => `[id=${JSON.stringify(id)}]`).join(', ');
      const menu = report.locator(linkedMenu || '.q-menu, .q-select__dialog, [role="listbox"]');
      const namedOptions = (linkedMenu ? menu : report).getByRole('option', { name: plantCode, exact: true });
      const namedItems = await visibleItems(namedOptions);
      const menuItems = namedItems.length
        ? namedItems
        : await visibleItems(menu.getByText(plantCode, { exact: true }));
      const items = menuItems.length || linkedMenu ? menuItems : await unlabelledPlantOptions(report, plantCode);
      if (items.length > 1) throw new FlowError(`Opção ${plantCode} ambígua.`);
      return items[0] || null;
    }, 15000).catch(error => {
      if (error instanceof WaitTimeout) throw new FlowError(`Abri o filtro Plant, mas não encontrei a opção ${plantCode}.`);
      throw error;
    });
    await option.click();
    if (input) {
      await waitFor(async () => await input.getAttribute('aria-expanded') !== 'true', 15000).catch(error => {
        if (error instanceof WaitTimeout) throw new FlowError(`A lista de plantas não fechou após clicar em ${plantCode}.`);
        throw error;
      });
    }
  }

  notify(`Opção ${plantCode} escolhida. Confirmando o valor no campo Plant.`);
  await waitFor(() => plant.evaluate((el, code) => {
    if (el.tagName === 'SELECT') return el.selectedOptions[0]?.textContent.trim() === code;
    const field = el.matches('input') ? el : el.querySelector('input');
    if (field?.value.trim() === code || el.innerText.trim() === code) return true;
    const select = el.closest('.q-select') || el.closest('.q-field');
    const native = select?.querySelector('.q-field__native');
    if (native?.innerText.trim() === code) return true;
    return Array.from(native?.querySelectorAll('span') || []).some(span =>
      span.getClientRects().length > 0
      && getComputedStyle(span).visibility === 'visible'
      && span.innerText.trim() === code
    );
  }, plantCode), 15000).catch(error => {
    if (error instanceof WaitTimeout) throw new FlowError(`O campo Plant não confirmou ${plantCode}. A busca não foi iniciada.`);
    throw error;
  });
  notify(`Plant ${plantCode} confirmada. Aguardando o botão Search ficar disponível.`);
  await waitFor(async () => !(await busy()) && await search.isVisible() && await search.isEnabled(), timeout).catch(error => {
    if (error instanceof WaitTimeout) throw new FlowError(`O botão Search não ficou disponível para a consulta da ${plantCode}.`);
    throw error;
  });
  const downloadWasEnabled = await downloadButton.isEnabled();
  try {
    await search.click();
  } catch (error) {
    if (error.name === 'TimeoutError') throw new FlowError('O navegador não conseguiu clicar em Search.');
    throw error;
  }
  notify(`Clique em Search concluído. Aguardando os resultados da ${plantCode}.`);
  try {
    // An enabled Download can belong to the previous search. Require a new loading cycle.
    await waitFor(async () => await busy() || (downloadWasEnabled && !(await downloadButton.isEnabled()))
      || (!downloadWasEnabled && await downloadButton.isEnabled()), timeout);
    await waitFor(async () => !(await busy()) && await search.isEnabled() && await downloadButton.isEnabled(), timeout);
  } catch (error) {
    if (error instanceof WaitTimeout) throw new FlowError(`Não foi possível confirmar a conclusão da busca da ${plantCode}.`);
    throw error;
  }
  if (!productionPlanPage(report)) throw new FlowError('A tela do relatório mudou durante a consulta.');
  notify(`Busca ${plantCode} concluída. Clicando em Download.`);
  const [download] = await Promise.all([
    report.waitForEvent('download', { timeout }),
    downloadButton.click(),
  ]);
  if (!/\.xlsx$/i.test(download.suggestedFilename())) throw new FlowError('O NFP não retornou um arquivo XLSX.');
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  const runDirectory = fs.mkdtempSync(path.join(directory, `${plantCode}-`));
  const file = path.join(runDirectory, `Production_Plan_${plantCode}.xlsx`);
  try {
    await download.saveAs(file);
    if (!fs.statSync(file).size) throw new FlowError('A planilha baixada está vazia.');
  } catch (error) {
    fs.rmSync(runDirectory, { recursive: true, force: true });
    throw error;
  }
  notify(`Planilha ${plantCode} salva em ${file}`);
  return file;
}

module.exports = { portalReady, openNfp, openProductionPlan, exportProductionPlan, FlowError, waitFor };
