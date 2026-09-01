import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';

import { SessionService } from '../core/session.service';

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
        next: () => void this.router.navigateByUrl('/profile'),
        error: () => this.error.set(true)
      });
  }
}
