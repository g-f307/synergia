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
    expect(logo.getAttribute('src')).toBe('/assets/logos/logo-negativa-horizontal.png');
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
    expect(logo.getAttribute('src')).toBe('/assets/logos/logo-horizontal.png');
    expect(logo.getAttribute('alt')).toBe('SYNERGIA');
    expect(fixture.nativeElement.querySelector('.login-visual')).toBeNull();
    expect(fixture.nativeElement.querySelector('.eyebrow')).toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('Acesso seguro');
  });

  it('anchors the locale selector to the login form on desktop', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();

    const form = fixture.nativeElement.querySelector('.login-form') as HTMLElement;
    const locale = fixture.nativeElement.querySelector('.login-locale') as HTMLElement;
    expect(getComputedStyle(form).position).toBe('relative');
    expect(getComputedStyle(locale).position).toBe('absolute');
    expect(locale.offsetParent).toBe(form);
  });
});
