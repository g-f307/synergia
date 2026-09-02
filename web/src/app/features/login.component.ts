import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { finalize } from 'rxjs';

import { SessionService } from '../core/session.service';

const INTERNAL_DESTINATIONS = ['/dashboard', '/imports', '/executions', '/search', '/workorders', '/lots', '/serials', '/pending-items', '/profile', '/admin'];
export function safeReturnUrl(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return '/profile';
  return INTERNAL_DESTINATIONS.some((path) => value === path || value.startsWith(`${path}/`) || value.startsWith(`${path}?`)) ? value : '/profile';
}

@Component({
  imports: [ReactiveFormsModule],
  template: `
    <section class="card narrow" aria-labelledby="login-title">
      <p class="eyebrow">Acesso seguro</p>
      <h1 id="login-title">Entrar no SYNERGIA</h1>
      <form [formGroup]="form" (ngSubmit)="submit()">
        <label>E-mail
          <input type="email" formControlName="email" autocomplete="username">
        </label>
        <label>Senha
          <input type="password" formControlName="password"
            autocomplete="current-password">
        </label>
        @if (error()) {
          <p class="error" role="alert">Credenciais inválidas ou serviço indisponível.</p>
        }
        <button type="submit" [disabled]="form.invalid || loading()">
          {{ loading() ? 'Entrando…' : 'Entrar' }}
        </button>
      </form>
    </section>`
})
export class LoginComponent {
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

  submit(): void {
    if (this.form.invalid) return;
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
