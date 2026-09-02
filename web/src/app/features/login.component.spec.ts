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
});
