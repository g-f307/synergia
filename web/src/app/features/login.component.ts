import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { finalize } from 'rxjs';

import { SessionService } from '../core/session.service';
import { ThemeService } from '../core/theme.service';
import { I18nService } from '../shared/i18n/i18n.service';

const INTERNAL_DESTINATIONS = ['/dashboard', '/imports', '/executions', '/search', '/workorders', '/lots', '/serials', '/pending-items', '/profile', '/admin'];
export function safeReturnUrl(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return '/profile';
  return INTERNAL_DESTINATIONS.some((path) => value === path || value.startsWith(`${path}/`) || value.startsWith(`${path}?`)) ? value : '/profile';
}

@Component({
  imports: [ReactiveFormsModule],
  template: `
    <div class="login-page">
    <section class="login-panel"><div class="login-form"><img class="login-logo" [src]="theme.brandLogo()" alt="SYNERGIA">
    <section class="card" aria-labelledby="login-title">
      <div class="login-locale">
        <label for="login-locale">{{ i18n.t('profile.locale') }}</label>
        <select id="login-locale" [value]="i18n.locale()" (change)="changeLocale($event)">
          <option value="pt-BR">PT</option>
          <option value="en-US">EN</option>
        </select>
      </div>
      <h1 id="login-title">{{ i18n.t('auth.title') }}</h1>
      <form [formGroup]="form" (ngSubmit)="submit()">
        <label for="login-email">{{ i18n.t('auth.email') }}</label>
        <input id="login-email" type="email" formControlName="email" autocomplete="username"
          [attr.aria-invalid]="form.controls.email.invalid && form.controls.email.touched"
          [attr.aria-describedby]="form.controls.email.invalid && form.controls.email.touched ? 'login-email-error' : null">
        @if (form.controls.email.invalid && form.controls.email.touched) {
          <p id="login-email-error" class="error">
            {{ i18n.t(form.controls.email.hasError('required') ? 'validation.required' : 'validation.email') }}
          </p>
        }
        <label for="login-password">{{ i18n.t('auth.password') }}</label>
        <input id="login-password" type="password" formControlName="password"
          autocomplete="current-password"
          [attr.aria-invalid]="form.controls.password.invalid && form.controls.password.touched"
          [attr.aria-describedby]="form.controls.password.invalid && form.controls.password.touched ? 'login-password-error' : null">
        @if (form.controls.password.invalid && form.controls.password.touched) {
          <p id="login-password-error" class="error">{{ i18n.t('validation.required') }}</p>
        }
        @if (error()) {
          <p class="error" role="alert">{{ i18n.t('auth.error') }}</p>
        }
        <button type="submit" [disabled]="loading()">
          {{ i18n.t(loading() ? 'auth.submitting' : 'auth.submit') }}
        </button>
      </form>
    </section></div></section>
    </div>`,
  styles: [`
    .login-form { padding-top: 3rem; position: relative; }
    .login-logo { display: block; margin-inline: auto; max-width: 13.75rem; width: 56%; }
    .login-locale { align-items: center; display: flex; gap: var(--space-2); position: absolute; right: var(--space-4); top: var(--space-4); }
    .login-locale label { color: var(--color-muted); display: block; font-size: .75rem; font-weight: 600; }
    .login-locale select { background: transparent; color: var(--color-muted); font-size: .8125rem; min-height: 2rem; padding: var(--space-1) var(--space-2); }
    @media (max-width: 30rem) {
      .login-form { padding-top: 0; }
      .login-locale { position: static; justify-content: flex-end; margin-bottom: var(--space-4); }
    }
  `]
})
export class LoginComponent {
  readonly i18n = inject(I18nService);
  readonly theme = inject(ThemeService);
  private readonly fb = inject(FormBuilder);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  readonly loading = signal(false);
  readonly error = signal(false);
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
    this.error.set(false);
    const { email, password } = this.form.getRawValue();
    this.session.login(email, password)
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: () => void this.router.navigateByUrl(safeReturnUrl(this.route.snapshot.queryParamMap.get('returnUrl'))),
        error: () => this.error.set(true)
      });
  }
}
