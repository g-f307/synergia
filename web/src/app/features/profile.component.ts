import { Component, effect, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';

import { SessionService } from '../core/session.service';

@Component({
  imports: [ReactiveFormsModule],
  template: `
    <section class="card" aria-labelledby="profile-title">
      <p class="eyebrow">Configuração pessoal</p>
      <h1 id="profile-title">Meu perfil</h1>
      @if (session.profile(); as profile) {
        <p>{{ profile.emails[0]?.email }}</p>
        <form [formGroup]="form" (ngSubmit)="save()">
          <label>Nome exibido <input formControlName="display_name"></label>
          <label>Idioma
            <select formControlName="locale">
              <option value="pt-BR">Português</option>
              <option value="en-US">English</option>
              <option value="es-ES">Español</option>
            </select>
          </label>
          <label>Fuso horário <input formControlName="timezone"></label>
          <label class="check">
            <input type="checkbox" formControlName="email"> Notificações por e-mail
          </label>
          <label class="check">
            <input type="checkbox" formControlName="in_app"> Notificações no sistema
          </label>
          <button type="submit" [disabled]="form.invalid || busy()">
            Salvar preferências
          </button>
        </form>
        <div class="avatar-panel">
          <h2>Foto do perfil</h2>
          <input type="file" accept="image/png,image/jpeg,image/webp"
            (change)="selectAvatar($event)">
          @if (profile.avatar) {
            <button class="secondary" type="button" (click)="removeAvatar()">
              Remover foto
            </button>
          }
        </div>
        @if (message()) { <p class="success" role="status">{{ message() }}</p> }
        @if (error()) {
          <p class="error" role="alert">Não foi possível concluir a alteração.</p>
        }
      }
    </section>`
})
export class ProfileComponent {
  readonly session = inject(SessionService);
  private readonly fb = inject(FormBuilder);
  readonly busy = signal(false);
  readonly error = signal(false);
  readonly message = signal('');
  readonly form = this.fb.nonNullable.group({
    display_name: ['', Validators.required],
    locale: ['pt-BR'],
    timezone: ['America/Manaus', Validators.required],
    email: [true],
    in_app: [true]
  });

  constructor() {
    effect(() => {
      const profile = this.session.profile();
      if (profile) {
        this.form.reset({
          display_name: profile.display_name,
          locale: profile.locale,
          timezone: profile.timezone,
          ...profile.notifications
        });
      }
    });
  }

  save(): void {
    const profile = this.session.profile();
    if (!profile || this.form.invalid) return;
    const value = this.form.getRawValue();
    this.begin();
    this.session.updateProfile({
      version: profile.version,
      display_name: value.display_name,
      locale: value.locale,
      timezone: value.timezone,
      notifications: { email: value.email, in_app: value.in_app }
    }).pipe(finalize(() => this.busy.set(false))).subscribe({
      next: () => this.message.set('Preferências salvas.'),
      error: () => this.error.set(true)
    });
  }

  selectAvatar(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.begin();
    this.session.uploadAvatar(file)
      .pipe(finalize(() => this.busy.set(false)))
      .subscribe({
        next: () => this.message.set('Foto atualizada.'),
        error: () => this.error.set(true)
      });
  }

  removeAvatar(): void {
    this.begin();
    this.session.removeAvatar()
      .pipe(finalize(() => this.busy.set(false)))
      .subscribe({
        next: () => this.message.set('Foto removida.'),
        error: () => this.error.set(true)
      });
  }

  private begin(): void {
    this.busy.set(true);
    this.error.set(false);
    this.message.set('');
  }
}
