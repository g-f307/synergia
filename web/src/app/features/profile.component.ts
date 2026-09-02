import { Component, DestroyRef, effect, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';

import { SessionService } from '../core/session.service';
import { I18nService } from '../shared/i18n/i18n.service';
import { isSupportedLocale } from '../shared/i18n/i18n.models';

@Component({
  imports: [ReactiveFormsModule],
  template: `
    <section class="card" aria-labelledby="profile-title">
      <p class="eyebrow">{{ i18n.t('profile.eyebrow') }}</p>
      <h1 id="profile-title">{{ i18n.t('profile.title') }}</h1>
      @if (session.profile(); as profile) {
        <p>{{ profile.emails[0]?.email }}</p>
        <form [formGroup]="form" (ngSubmit)="save()">
          <label for="profile-display-name">{{ i18n.t('profile.displayName') }}</label>
          <input id="profile-display-name" formControlName="display_name"
            [attr.aria-invalid]="form.controls.display_name.invalid && form.controls.display_name.touched"
            [attr.aria-describedby]="form.controls.display_name.invalid && form.controls.display_name.touched ? 'profile-display-name-error' : null">
          @if (form.controls.display_name.invalid && form.controls.display_name.touched) {
            <p id="profile-display-name-error" class="error">{{ i18n.t('validation.required') }}</p>
          }
          <label>{{ i18n.t('profile.locale') }}
            <select formControlName="locale">
              <option value="pt-BR">{{ i18n.t('profile.locale.ptBR') }}</option>
              <option value="en-US">{{ i18n.t('profile.locale.enUS') }}</option>
            </select>
          </label>
          <label for="profile-timezone">{{ i18n.t('profile.timezone') }}</label>
          <input id="profile-timezone" formControlName="timezone"
            [attr.aria-invalid]="form.controls.timezone.invalid && form.controls.timezone.touched"
            [attr.aria-describedby]="form.controls.timezone.invalid && form.controls.timezone.touched ? 'profile-timezone-error' : null">
          @if (form.controls.timezone.invalid && form.controls.timezone.touched) {
            <p id="profile-timezone-error" class="error">{{ i18n.t('validation.required') }}</p>
          }
          <label class="check">
            <input type="checkbox" formControlName="email"> {{ i18n.t('profile.emailNotifications') }}
          </label>
          <label class="check">
            <input type="checkbox" formControlName="in_app"> {{ i18n.t('profile.inAppNotifications') }}
          </label>
          <button type="submit" [disabled]="busy()">
            {{ i18n.t('profile.save') }}
          </button>
        </form>
        <div class="avatar-panel">
          <h2>{{ i18n.t('profile.avatarTitle') }}</h2>
          @if (avatarUrl(); as source) {
            <img class="avatar-preview" [src]="source" [alt]="i18n.t('profile.avatarAlt')">
          }
          <label>{{ i18n.t('profile.avatarInput') }}
            <input type="file" accept="image/png,image/jpeg,image/webp"
              (change)="selectAvatar($event)">
          </label>
          @if (profile.avatar) {
            <button class="secondary" type="button" (click)="removeAvatar()">
              {{ i18n.t('profile.avatarRemove') }}
            </button>
          }
        </div>
        @if (message()) { <p class="success" role="status">{{ message() }}</p> }
        @if (error()) {
          <p class="error" role="alert">{{ i18n.t('profile.error') }}</p>
        }
      }
    </section>`
})
export class ProfileComponent {
  readonly session = inject(SessionService);
  readonly i18n = inject(I18nService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  readonly busy = signal(false);
  readonly error = signal(false);
  readonly message = signal('');
  readonly avatarUrl = signal<string | null>(null);
  private loadedAvatarSha?: string;
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
          locale: isSupportedLocale(profile.locale) ? profile.locale : 'pt-BR',
          timezone: profile.timezone,
          ...profile.notifications
        });
        if (profile.avatar && profile.avatar.sha256 !== this.loadedAvatarSha) {
          this.loadAvatar(profile.avatar.sha256);
        } else if (!profile.avatar) {
          this.clearAvatar();
        }
      }
    });
    this.destroyRef.onDestroy(() => this.clearAvatar());
  }

  save(): void {
    const profile = this.session.profile();
    if (!profile || this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    this.begin();
    this.session.updateProfile({
      version: profile.version,
      display_name: value.display_name,
      locale: value.locale,
      timezone: value.timezone,
      notifications: { email: value.email, in_app: value.in_app }
    }).pipe(finalize(() => this.busy.set(false))).subscribe({
      next: () => this.message.set(this.i18n.t('profile.saved')),
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
        next: (profile) => {
          this.message.set(this.i18n.t('profile.avatarUpdated'));
          if (profile.avatar) this.loadAvatar(profile.avatar.sha256);
        },
        error: () => this.error.set(true)
      });
  }

  removeAvatar(): void {
    this.begin();
    this.session.removeAvatar()
      .pipe(finalize(() => this.busy.set(false)))
      .subscribe({
        next: () => {
          this.clearAvatar();
          this.message.set(this.i18n.t('profile.avatarRemoved'));
        },
        error: () => this.error.set(true)
      });
  }

  private begin(): void {
    this.busy.set(true);
    this.error.set(false);
    this.message.set('');
  }

  private loadAvatar(sha256: string): void {
    this.session.loadAvatar().subscribe({
      next: (blob) => {
        this.clearAvatar();
        this.avatarUrl.set(URL.createObjectURL(blob));
        this.loadedAvatarSha = sha256;
      },
      error: () => this.error.set(true)
    });
  }

  private clearAvatar(): void {
    const current = this.avatarUrl();
    if (current) URL.revokeObjectURL(current);
    this.avatarUrl.set(null);
    this.loadedAvatarSha = undefined;
  }
}
