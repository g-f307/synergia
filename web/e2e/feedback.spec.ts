import AxeBuilder from '@axe-core/playwright';
import { expect, test, Page, TestInfo } from '@playwright/test';
import { execFileSync } from 'node:child_process';

const password = 'synthetic-e2e-password-63';
async function login(page: Page, user = 'operator') {
  const email=user+'.e2e@example.invalid';
  execFileSync(process.env.E2E_PYTHON ?? 'python',['../scripts/bootstrap_web_e2e.py','--revoke-email',email],{env:process.env});
  await page.goto('/login');
  await page.getByLabel(/e-mail|email/i).fill(email);
  await page.getByLabel(/senha|password/i).fill(password);
  await page.getByRole('button',{name:/entrar|sign in/i}).click();
  await expect(page).toHaveURL(/\/profile/);
}
async function evidence(page: Page, info: TestInfo, name: string) {
  await page.screenshot({path:info.outputPath(name+'.png'),fullPage:true});
  await info.attach(name,{path:info.outputPath(name+'.png'),contentType:'image/png'});
}
async function accessible(page: Page) {
  const results=await new AxeBuilder({page}).include('.feedback-page').analyze();
  expect(results.violations.filter(v=>['serious','critical'].includes(v.impact??''))).toEqual([]);
}

test('global entry, accessible form, themes and narrow viewport', async ({page},info) => {
  await login(page);
  await page.getByRole('link',{name:'Enviar feedback',exact:true}).click();
  await expect(page.getByLabel('Título',{exact:false})).toBeVisible();
  await expect(page.locator('#source')).toHaveValue('profile');
  await accessible(page);
  await evidence(page,info,'principal-light');
  await page.getByRole('button',{name:/alternar tema/i}).click();
  await accessible(page); await evidence(page,info,'principal-dark');
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('#title')).toBeVisible();
  for (const selector of ['.feedback-page', '#title', '.logout-button']) {
    const box=await page.locator(selector).boundingBox();
    expect(box).not.toBeNull();expect(box!.x+box!.width).toBeLessThanOrEqual(391);
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.locator('#title').focus(); await page.keyboard.press('Tab');
  await expect(page.locator('#description')).toBeFocused();
  await accessible(page);await evidence(page,info,'principal-mobile');
});

test('author sends bug, manager triages, stale update conflicts and author follows history', async ({page,browser},info) => {
  test.setTimeout(90_000);
  await login(page);
  await page.getByRole('link',{name:'Enviar feedback',exact:true}).click();
  const title='Synthetic feedback '+Date.now();
  await page.locator('#title').fill(title);
  await page.locator('#description').fill('<script>window.feedbackInjected=true</script> Synthetic steps to reproduce');
  await page.locator('#expected').fill('Expected synthetic result');
  await page.locator('#observed').fill('Observed synthetic result');
  await page.getByRole('button',{name:'Enviar feedback',exact:true}).click();
  await expect(page.getByText('Feedback recebido',{exact:true})).toBeVisible();
  const protocol=await page.locator('.protocol').innerText();
  expect(protocol).toMatch(/^FB-[A-F0-9]{32}$/);
  await evidence(page,info,'confirmation');
  await page.getByRole('link',{name:'Acompanhar registro'}).click();
  await expect(page).toHaveURL(/\/feedback\/[a-f0-9-]{36}$/);
  const id=page.url().split('/').pop()!;
  await expect(page.locator('.detail .plain').first()).toContainText('<script>');
  expect(await page.evaluate(()=>('feedbackInjected' in window))).toBeFalsy();
  const manager=await browser.newContext();const managerPage=await manager.newPage();
  try {
    await login(managerPage,'manager');
    await managerPage.getByRole('link',{name:'Feedback triage',exact:true}).click();
    await managerPage.locator('.filters summary').click();
    await managerPage.locator('input[name=protocol]').fill(protocol);
    await managerPage.getByRole('button',{name:'Apply filters'}).click();
    await managerPage.getByRole('link',{name:title,exact:true}).click();
    const stale=await manager.newPage();await stale.goto('/feedback/triage/'+id);
    await expect(stale.locator('#state')).toBeVisible();
    await managerPage.locator('#state').selectOption('under_review');
    await managerPage.getByRole('button',{name:'Save decision'}).click();
    await expect(managerPage.getByText('Decision saved and recorded in history.')).toBeVisible();
    await stale.locator('#state').selectOption('discarded');
    await stale.locator('#reason').fill('Synthetic stale decision');
    await stale.getByRole('button',{name:'Save decision'}).click();
    await expect(stale.getByText(/record was updated/)).toBeVisible();
    await expect(stale.getByRole('button',{name:'Save decision'})).toBeDisabled();
    await stale.getByRole('button',{name:'Reload',exact:true}).click();
    await expect(stale.locator('.detail .badge').last()).toHaveText('Under review');
    await managerPage.locator('#state').selectOption('resolved');
    await managerPage.locator('#reason').fill('Resolved after synthetic verification');
    await managerPage.getByRole('button',{name:'Save decision'}).click();
    await expect(managerPage.locator('.detail .badge').last()).toHaveText('Resolved');
    await accessible(managerPage);await evidence(managerPage,info,'triage-history');
    await page.getByRole('button',{name:'Recarregar',exact:true}).click();
    await expect(page.locator('.detail .badge').last()).toHaveText('Resolvido');
    await expect(page.getByText('Resolved after synthetic verification',{exact:true})).toBeVisible();
    await page.getByRole('link',{name:'Voltar à lista'}).click();
    await expect(page.getByRole('link',{name:title,exact:true})).toBeVisible();
  } finally {await manager.close();}
});

test('reader from another organization has an empty inbox and no triage access', async ({page},info) => {
  await login(page,'reader');await page.goto('/feedback');
  await expect(page.getByText('No feedback found',{exact:true})).toBeVisible();
  await evidence(page,info,'empty');
  await expect(page.getByRole('link',{name:'Feedback triage',exact:true})).toHaveCount(0);
  await page.goto('/feedback/triage');await expect(page).toHaveURL(/\/profile/);
});

test('temporary API failure keeps text and presents an accessible error', async ({page},info) => {
  await login(page);await page.goto('/feedback/new');
  await page.locator('#title').fill('Synthetic unsent bug');
  await page.locator('#description').fill('Synthetic text preserved after failed submission');
  await page.route('**/feedback',async route=>{
    if(route.request().method()==='POST') await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'feedback_unavailable',message:'Synthetic outage',details:{}}})});
    else await route.continue();
  });
  await page.getByRole('button',{name:'Enviar feedback',exact:true}).click();
  await expect(page.locator('[data-state=error]')).toBeInViewport();
  await expect(page.locator('.feedback-page div[tabindex="-1"]')).toBeFocused();
  await expect(page.locator('#description')).toHaveValue('Synthetic text preserved after failed submission');
  await accessible(page);await evidence(page,info,'error');
});

test('profile preference enables the Spanish feedback journey', async ({page},info) => {
  await login(page);
  await page.locator('#profile-locale').selectOption('es-ES');
  await page.locator('form button[type=submit]').first().click();
  await expect(page.locator('html')).toHaveAttribute('lang','es-ES');
  await page.goto('/feedback/new');
  await expect(page.getByRole('button',{name:'Enviar comentarios',exact:true})).toBeVisible();
  await expect(page.locator('label[for=description]')).toHaveText(/Descripción/);
  await page.locator('#kind').selectOption('suggestion');
  await expect(page.locator('#expected')).toHaveCount(0);
  await accessible(page);await evidence(page,info,'spanish');
  await page.goto('/profile');await page.locator('#profile-locale').selectOption('pt-BR');await page.locator('form button[type=submit]').first().click();
});
