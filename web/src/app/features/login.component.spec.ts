import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { NEVER, throwError } from 'rxjs';

import { SessionService } from '../core/session.service';
import { I18nService } from '../shared/i18n/i18n.service';
import { LoginComponent, safeReturnUrl } from './login.component';

describe('safeReturnUrl', () => {
  it('accepts only known internal destinations', () => {
    expect(safeReturnUrl('/executions/exec-1?tab=history')).toBe('/executions/exec-1?tab=history');
    expect(safeReturnUrl('/pending-items')).toBe('/pending-items');
    expect(safeReturnUrl('/reports/report-1')).toBe('/reports/report-1');
  });

  it('rejects external, protocol-relative and unknown destinations', () => {
    expect(safeReturnUrl('https://example.invalid')).toBe('/profile');
    expect(safeReturnUrl('//example.invalid/path')).toBe('/profile');
    expect(safeReturnUrl('/%2Fexample.invalid/path')).toBe('/profile');
    expect(safeReturnUrl('/login')).toBe('/profile');
  });
});

describe('LoginComponent', () => {
  const session = {
    state: signal('anonymous'),
    login: jasmine.createSpy('login').and.returnValue(NEVER)
  };

  beforeEach(async () => {
    document.documentElement.dataset['theme'] = 'light';
    session.login.calls.reset();
    session.login.and.returnValue(NEVER);
    session.state.set('anonymous');
    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideRouter([]),
        { provide: SessionService, useValue: session }
      ]
    }).compileComponents();
    TestBed.inject(I18nService).configure('pt-BR');
  });

  it('reports rejected credentials for a 401 login response', () => {
    session.login.and.returnValue(throwError(() => new HttpErrorResponse({ status: 401 })));
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.componentInstance.form.setValue({
      email: 'anonymous@example.invalid',
      password: 'wrong-password'
    });
    fixture.componentInstance.submit();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain('Credenciais inválidas');
  });

  it('reports authentication unavailability for network and server failures', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.componentInstance.form.setValue({
      email: 'anonymous@example.invalid',
      password: 'synthetic-password'
    });

    session.login.and.returnValue(throwError(() => new HttpErrorResponse({ status: 0 })));
    fixture.componentInstance.submit();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain('indisponível');

    session.login.and.returnValue(throwError(() => new HttpErrorResponse({ status: 503 })));
    fixture.componentInstance.submit();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain('indisponível');
  });

  it('asks the user to wait after a rate-limited login response', () => {
    session.login.and.returnValue(throwError(() => new HttpErrorResponse({ status: 429 })));
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.componentInstance.form.setValue({
      email: 'anonymous@example.invalid',
      password: 'synthetic-password'
    });

    fixture.componentInstance.submit();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role=alert]').textContent)
      .toContain('Muitas tentativas');
  });

  it('uses a generic rejection message for other client errors', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.componentInstance.form.setValue({
      email: 'anonymous@example.invalid',
      password: 'synthetic-password'
    });

    session.login.and.returnValue(throwError(() => new HttpErrorResponse({ status: 403 })));
    fixture.componentInstance.submit();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent)
      .toContain('Não foi possível concluir o acesso');

    session.login.and.returnValue(throwError(() => new HttpErrorResponse({ status: 422 })));
    fixture.componentInstance.submit();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent)
      .toContain('Não foi possível concluir o acesso');
  });

  it('explains that the prior session expired before asking for credentials again', () => {
    session.state.set('expired');
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain('sessão expirou');
  });

  it('updates the login brand when the active theme changes', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    fixture.componentInstance.theme.toggle();
    fixture.detectChanges();

    const logo = fixture.nativeElement.querySelector('.login-logo') as HTMLImageElement;
    expect(logo.getAttribute('src')).toBe('/assets/logos/synergia-logo-vertical.svg');
  });

  it('allows an anonymous user to display and use login in English', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    const locale = fixture.nativeElement.querySelector('#login-locale') as HTMLSelectElement;
    locale.value = 'en-US';
    locale.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    fixture.componentInstance.form.setValue({
      email: 'anonymous@example.invalid',
      password: 'synthetic-password'
    });
    fixture.componentInstance.submit();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('h1').textContent).toContain('Sign in');
    expect(fixture.nativeElement.querySelector('button[type=submit]').textContent).toContain('Signing in');
    expect(document.documentElement.lang).toBe('en-US');
    expect(session.login).toHaveBeenCalledWith(
      'anonymous@example.invalid',
      'synthetic-password'
    );
  });

  it('uses the approved brand asset without redundant promotional content', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    const logo = fixture.nativeElement.querySelector('.login-logo') as HTMLImageElement;
    expect(logo.getAttribute('src')).toBe('/assets/logos/synergia-logo-vertical.svg');
    expect(logo.getAttribute('alt')).toBe('SYNERGIA');
    expect(fixture.nativeElement.querySelector('.login-visual')).toBeNull();
    expect(fixture.nativeElement.querySelector('.eyebrow')).toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('Acesso seguro');
  });

  it('uses a single framed surface with a dedicated brand area', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll('.login-shell').length).toBe(1);
    expect(fixture.nativeElement.querySelector('.login-brand')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.card')).toBeNull();
  });

  it('centers the form when it fits and keeps its start reachable when it overflows', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    const access = (fixture.nativeElement.querySelector('.login-access') as HTMLElement)
      .getBoundingClientRect();
    const content = (fixture.nativeElement.querySelector('.login-content') as HTMLElement)
      .getBoundingClientRect();
    const accessCenter = access.top + access.height / 2;
    const contentCenter = content.top + content.height / 2;

    expect(window.innerWidth).toBeGreaterThan(760);
    if (content.height <= access.height) {
      expect(Math.abs(contentCenter - accessCenter)).toBeLessThanOrEqual(1);
    } else {
      expect(content.top).toBeGreaterThanOrEqual(access.top);
      expect((fixture.nativeElement.querySelector('.login-access') as HTMLElement).scrollHeight)
        .toBeGreaterThan((fixture.nativeElement.querySelector('.login-access') as HTMLElement).clientHeight);
    }
  });

  it('centers the framed surface when desktop spacing reaches its maximum', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    const page = fixture.nativeElement.querySelector('.login-page') as HTMLElement;
    page.style.padding = '52px';
    page.style.setProperty('--login-page-gap', '52px');

    const pageBounds = page.getBoundingClientRect();
    const shellBounds = (fixture.nativeElement.querySelector('.login-shell') as HTMLElement)
      .getBoundingClientRect();
    const pageCenter = pageBounds.top + pageBounds.height / 2;
    const shellCenter = shellBounds.top + shellBounds.height / 2;
    const availableHeight = pageBounds.height - 104;

    expect(window.innerWidth).toBeGreaterThan(760);
    expect(shellBounds.height).toBeLessThanOrEqual(availableHeight);
    expect(Math.abs(shellCenter - pageCenter)).toBeLessThanOrEqual(1);
  });

  it('keeps overflow reachable when zoom reduces the available height', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    const page = fixture.nativeElement.querySelector('.login-page') as HTMLElement;
    const access = fixture.nativeElement.querySelector('.login-access') as HTMLElement;

    expect(getComputedStyle(page).overflowY).toBe('auto');
    expect(getComputedStyle(access).overflowY).toBe('auto');
  });

  it('groups language and theme controls in the login utility area', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    const utility = fixture.nativeElement.querySelector('.login-utility') as HTMLElement;
    const locale = utility.querySelector('#login-locale') as HTMLSelectElement;
    const localeControl = utility.querySelector('.locale-select') as HTMLElement;
    const localeName = utility.querySelector('.locale-name') as HTMLElement;
    const localeBadge = utility.querySelector('.locale-badge') as HTMLElement;
    const theme = utility.querySelector('.login-theme') as HTMLButtonElement;

    expect(locale).not.toBeNull();
    expect(localeControl).not.toBeNull();
    expect(localeName.textContent?.trim()).toBe('Idioma');
    expect(localeBadge.querySelector('svg')).not.toBeNull();
    expect(getComputedStyle(localeBadge).borderStyle).toBe('none');
    expect(getComputedStyle(locale).appearance).toBe('none');
    expect(Number.parseInt(getComputedStyle(locale).fontWeight, 10)).toBeGreaterThanOrEqual(700);
    expect(theme.getAttribute('aria-label')).toBe('Alternar tema');

    theme.click();
    fixture.detectChanges();

    expect(document.documentElement.dataset['theme']).toBe('dark');
    expect((fixture.nativeElement.querySelector('.login-logo') as HTMLImageElement).getAttribute('src'))
      .toBe('/assets/logos/synergia-logo-vertical.svg');
  });
});
