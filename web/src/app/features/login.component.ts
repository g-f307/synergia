import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { finalize } from 'rxjs';

import { SessionService } from '../core/session.service';
import { safeReturnUrl } from '../core/auth-navigation';
import { ThemeService } from '../core/theme.service';
import { I18nService } from '../shared/i18n/i18n.service';

type LoginMessageKey =
  | 'auth.errorCredentials'
  | 'auth.errorExpired'
  | 'auth.errorRateLimited'
  | 'auth.errorRequest'
  | 'auth.errorUnavailable';

export { safeReturnUrl } from '../core/auth-navigation';

@Component({
  imports: [ReactiveFormsModule],
  template: `
    <main class="login-page">
      <section class="login-shell" aria-labelledby="login-title">
        <div class="login-brand" aria-label="SYNERGIA">
          <img class="login-logo" [src]="theme.verticalBrandLogo()" alt="SYNERGIA">
        </div>

        <div class="login-access">
          <header class="login-utility">
            <label class="login-locale" for="login-locale">
              <span class="locale-badge" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false">
                  <circle cx="12" cy="12" r="8.5"></circle>
                  <path d="M3.8 12h16.4M12 3.5c2.2 2.4 3.3 5.2 3.3 8.5S14.2 18.1 12 20.5M12 3.5C9.8 5.9 8.7 8.7 8.7 12s1.1 6.1 3.3 8.5"></path>
                </svg>
              </span>
              <span class="locale-name">{{ i18n.t('profile.locale') }}</span>
              <span class="locale-select">
                <select id="login-locale" [value]="i18n.locale()" (change)="changeLocale($event)">
                  <option value="pt-BR">PT</option>
                  <option value="en-US">EN</option>
                </select>
              </span>
            </label>
            <button type="button" class="login-theme" (click)="theme.toggle()"
              [attr.aria-label]="i18n.t('accessibility.toggleTheme')">
              <span aria-hidden="true">◐</span>
            </button>
          </header>

          <div class="login-content">
            <div class="login-heading">
              <h1 id="login-title">{{ i18n.t('auth.title') }}</h1>
            </div>

            <form class="login-form" [formGroup]="form" (ngSubmit)="submit()" novalidate>
              <div class="login-field">
                <label for="login-email">{{ i18n.t('auth.email') }}</label>
                <input id="login-email" type="email" formControlName="email" autocomplete="username"
                  [attr.aria-invalid]="form.controls.email.invalid && form.controls.email.touched"
                  [attr.aria-describedby]="form.controls.email.invalid && form.controls.email.touched ? 'login-email-error' : null">
                @if (form.controls.email.invalid && form.controls.email.touched) {
                  <p id="login-email-error" class="error">
                    {{ i18n.t(form.controls.email.hasError('required') ? 'validation.required' : 'validation.email') }}
                  </p>
                }
              </div>

              <div class="login-field">
                <label for="login-password">{{ i18n.t('auth.password') }}</label>
                <input id="login-password" type="password" formControlName="password"
                  autocomplete="current-password"
                  [attr.aria-invalid]="form.controls.password.invalid && form.controls.password.touched"
                  [attr.aria-describedby]="form.controls.password.invalid && form.controls.password.touched ? 'login-password-error' : null">
                @if (form.controls.password.invalid && form.controls.password.touched) {
                  <p id="login-password-error" class="error">{{ i18n.t('validation.required') }}</p>
                }
              </div>

              @if (errorKey(); as messageKey) {
                <p class="login-error error" role="alert">{{ i18n.t(messageKey) }}</p>
              }

              <button class="login-submit" type="submit" [disabled]="loading()">
                {{ i18n.t(loading() ? 'auth.submitting' : 'auth.submit') }}
              </button>
            </form>
          </div>
        </div>
      </section>
    </main>`,
  styleUrl: './login.component.css'
})
export class LoginComponent {
  readonly i18n = inject(I18nService);
  readonly theme = inject(ThemeService);
  private readonly fb = inject(FormBuilder);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  readonly loading = signal(false);
  readonly errorKey = signal<LoginMessageKey | null>(this.sessionStateMessage());
  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required]
  });

  changeLocale(event: Event): void {
    this.i18n.configure((event.target as HTMLSelectElement).value);
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.loading.set(true);
    this.errorKey.set(null);
    const { email, password } = this.form.getRawValue();
    this.session.login(email, password)
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: () => void this.router.navigateByUrl(safeReturnUrl(this.route.snapshot.queryParamMap.get('returnUrl'))),
        error: (error: HttpErrorResponse) => this.errorKey.set(this.loginErrorMessage(error))
      });
  }

  private loginErrorMessage(error: HttpErrorResponse): LoginMessageKey {
    if (error.status === 401) return 'auth.errorCredentials';
    if (error.status === 429) return 'auth.errorRateLimited';
    if (error.status === 0 || error.status >= 500) return 'auth.errorUnavailable';
    return 'auth.errorRequest';
  }

  private sessionStateMessage(): LoginMessageKey | null {
    if (this.session.state() === 'expired') return 'auth.errorExpired';
    if (this.session.state() === 'unavailable') return 'auth.errorUnavailable';
    return null;
  }
}
