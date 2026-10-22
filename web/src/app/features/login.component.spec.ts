import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { NEVER } from 'rxjs';

import { SessionService } from '../core/session.service';
import { I18nService } from '../shared/i18n/i18n.service';
import { LoginComponent, safeReturnUrl } from './login.component';

describe('safeReturnUrl', () => {
  it('accepts only known internal destinations', () => {
    expect(safeReturnUrl('/executions/exec-1?tab=history')).toBe('/executions/exec-1?tab=history');
    expect(safeReturnUrl('/pending-items')).toBe('/pending-items');
  });

  it('rejects external, protocol-relative and unknown destinations', () => {
    expect(safeReturnUrl('https://example.invalid')).toBe('/profile');
    expect(safeReturnUrl('//example.invalid/path')).toBe('/profile');
    expect(safeReturnUrl('/reports')).toBe('/profile');
  });
});

describe('LoginComponent', () => {
  const session = { login: jasmine.createSpy('login').and.returnValue(NEVER) };

  beforeEach(async () => {
    document.documentElement.dataset['theme'] = 'light';
    session.login.calls.reset();
    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideRouter([]),
        { provide: SessionService, useValue: session }
      ]
    }).compileComponents();
    TestBed.inject(I18nService).configure('pt-BR');
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
