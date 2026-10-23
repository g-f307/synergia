import { Component, DestroyRef, effect, inject, signal, untracked } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';

import { SessionService } from '../core/session.service';
import { I18nService } from '../shared/i18n/i18n.service';
import { isSupportedLocale } from '../shared/i18n/i18n.models';
import { SessionsComponent } from './sessions.component';

@Component({
  imports: [ReactiveFormsModule, SessionsComponent],
  template: `
    <section class="profile-page" aria-labelledby="profile-title">
      <h1 id="profile-title" class="sr-only">{{ i18n.t('profile.title') }}</h1>
      @if (session.profile(); as profile) {
        <div class="profile-grid">
          <aside class="avatar-panel">
            <div class="avatar-stage">
              <div class="avatar-orbit" aria-hidden="true"></div>
              <div class="avatar-frame">
                @if (avatarUrl(); as source) {
                  <img class="avatar-preview" [src]="source" [alt]="i18n.t('profile.avatarAlt')" width="160" height="160">
                } @else {
                  <span class="avatar-fallback" aria-hidden="true">{{ profile.display_name.charAt(0) || 'S' }}</span>
                }
              </div>
            </div>
            <div class="identity-copy"><h2>{{ profile.display_name }}</h2><p>{{ profile.emails[0]?.email }}</p></div>
            <div class="avatar-actions">
              <label class="upload-button" for="profile-avatar-input">{{ i18n.t('profile.avatarInput') }}</label>
              <input id="profile-avatar-input" class="file-input" name="avatar" type="file" accept="image/png,image/jpeg,image/webp" (change)="selectAvatar($event)">
              @if (profile.avatar || avatarUrl()) {
                <button class="secondary" type="button" (click)="removeAvatar()">{{ i18n.t('profile.avatarRemove') }}</button>
              }
            </div>
          </aside>
          <section class="profile-settings" aria-labelledby="preferences-title">
            <header><h2 id="preferences-title">{{ i18n.t('profile.title') }}</h2><p class="profile-email">{{ profile.emails[0]?.email }}</p></header>
            <form [formGroup]="form" (ngSubmit)="save()">
              <div class="field"><label for="profile-display-name">{{ i18n.t('profile.displayName') }}</label><input id="profile-display-name" name="display_name" autocomplete="name" formControlName="display_name" [attr.aria-invalid]="form.controls.display_name.invalid && form.controls.display_name.touched" [attr.aria-describedby]="form.controls.display_name.invalid && form.controls.display_name.touched ? 'profile-display-name-error' : null">@if (form.controls.display_name.invalid && form.controls.display_name.touched) {<p id="profile-display-name-error" class="error">{{ i18n.t('validation.required') }}</p>}</div>
              <div class="field"><label for="profile-locale">{{ i18n.t('profile.locale') }}</label><select id="profile-locale" name="locale" formControlName="locale"><option value="pt-BR">{{ i18n.t('profile.locale.ptBR') }}</option><option value="en-US">{{ i18n.t('profile.locale.enUS') }}</option></select></div>
              <div class="field field-wide"><label for="profile-timezone">{{ i18n.t('profile.timezone') }}</label><input id="profile-timezone" name="timezone" autocomplete="off" formControlName="timezone" [attr.aria-invalid]="form.controls.timezone.invalid && form.controls.timezone.touched" [attr.aria-describedby]="form.controls.timezone.invalid && form.controls.timezone.touched ? 'profile-timezone-error' : null">@if (form.controls.timezone.invalid && form.controls.timezone.touched) {<p id="profile-timezone-error" class="error">{{ i18n.t('validation.required') }}</p>}</div>
              <fieldset class="notification-options"><legend>{{ i18n.t('navigation.notifications') }}</legend><label class="check"><input type="checkbox" formControlName="email"> <span>{{ i18n.t('profile.emailNotifications') }}</span></label><label class="check"><input type="checkbox" formControlName="in_app"> <span>{{ i18n.t('profile.inAppNotifications') }}</span></label></fieldset>
              <fieldset class="appearance-options"><legend>{{ i18n.t('profile.appearance') }}</legend><div class="field"><label for="profile-density">{{ i18n.t('profile.density') }}</label><select id="profile-density" name="density" formControlName="density"><option value="comfortable">{{ i18n.t('profile.density.comfortable') }}</option><option value="compact">{{ i18n.t('profile.density.compact') }}</option></select></div><div class="field"><label for="profile-font-scale">{{ i18n.t('profile.fontScale') }}</label><select id="profile-font-scale" name="font_scale" formControlName="font_scale"><option value="small">{{ i18n.t('profile.fontScale.small') }}</option><option value="normal">{{ i18n.t('profile.fontScale.normal') }}</option><option value="large">{{ i18n.t('profile.fontScale.large') }}</option></select></div></fieldset>
              <div class="form-actions"><button type="submit" [disabled]="busy()">{{ i18n.t('profile.save') }}</button></div>
            </form>
          </section>
        </div>
        <syn-sessions />
        @if (message()) { <p class="success floating-message" role="status" aria-live="polite">{{ message() }}</p> }
        @if (error()) {
          <p class="error" role="alert">{{ i18n.t('profile.error') }}</p>
        }
      }
    </section>`,
  styles: [`
    :host{display:block;height:100%;min-height:0}.profile-page{--line:color-mix(in srgb,var(--syn-text) 9%,transparent);background:var(--syn-bg-card);border:1px solid var(--line);border-radius:28px;display:grid;gap:22px;height:100%;min-height:0;overflow-x:hidden;overflow-y:auto;padding:clamp(20px,2.5vw,34px);scrollbar-gutter:stable}.sr-only{clip:rect(0,0,0,0);clip-path:inset(50%);height:1px;overflow:hidden;position:absolute;white-space:nowrap;width:1px}.profile-grid{display:grid;gap:20px;grid-template-columns:minmax(15rem,.7fr) minmax(0,1.7fr)}.avatar-panel,.profile-settings{background:var(--syn-bg);border:1px solid var(--line);border-radius:20px}.avatar-panel{align-content:start;display:grid;justify-items:center;padding:clamp(24px,3vw,40px);text-align:center}.avatar-stage{display:grid;height:190px;isolation:isolate;margin-bottom:18px;place-items:center;position:relative;width:190px}.avatar-orbit{background:conic-gradient(from 45deg,color-mix(in srgb,var(--syn-primary) 70%,transparent),transparent 34%,color-mix(in srgb,var(--syn-primary) 20%,transparent) 62%,transparent);border-radius:50%;inset:0;opacity:.7;position:absolute}.avatar-stage::before{background:color-mix(in srgb,var(--syn-primary) 7%,var(--syn-bg-card));border:1px solid color-mix(in srgb,var(--syn-primary) 14%,transparent);border-radius:50%;content:"";inset:9px;position:absolute}.avatar-frame{align-items:center;background:var(--syn-primary);border:6px solid var(--syn-bg-card);border-radius:50%;box-shadow:0 14px 32px color-mix(in srgb,var(--syn-primary) 18%,transparent);display:flex;height:160px;justify-content:center;overflow:hidden;position:relative;width:160px;z-index:1}.avatar-preview{height:100%;margin:0;object-fit:cover;width:100%}.avatar-fallback{color:#fff;font-family:LGEIHeadline,sans-serif;font-size:4.5rem;font-weight:700}.identity-copy h2,.identity-copy p,.profile-settings header h2,.profile-settings header p{margin:0}.identity-copy h2{font-size:1.25rem;text-wrap:balance}.identity-copy p,.profile-email{color:var(--syn-text-secondary);font-size:.82rem;margin-top:5px;overflow-wrap:anywhere}.avatar-actions{display:grid;gap:10px;margin-top:24px;width:100%}.file-input{clip:rect(0,0,0,0);clip-path:inset(50%);height:1px;overflow:hidden;position:absolute;white-space:nowrap;width:1px}.upload-button{align-items:center;background:var(--syn-primary);border:1px solid var(--syn-primary);border-radius:999px;color:#fff;cursor:pointer;display:flex;font-size:.85rem;font-weight:700;justify-content:center;min-height:44px;padding:10px 16px}.file-input:focus-visible+.upload-button,.upload-button:focus-visible{outline:3px solid color-mix(in srgb,var(--syn-primary) 34%,transparent);outline-offset:3px}.avatar-actions .secondary{border-radius:999px;width:100%}.profile-settings{padding:clamp(22px,3vw,34px)}.profile-settings>header{border-bottom:1px solid var(--line);margin-bottom:24px;padding-bottom:20px}.profile-settings header h2{font-size:1.35rem}.profile-settings form{display:grid;gap:18px;grid-template-columns:repeat(2,minmax(0,1fr))}.field{display:grid;gap:7px;min-width:0}.field-wide,.notification-options,.appearance-options,.form-actions{grid-column:1/-1}.field label,legend{font-size:.78rem;font-weight:700}.field input,.field select{background:var(--syn-bg-card);color:var(--syn-text);min-height:44px;width:100%}.notification-options,.appearance-options{border:1px solid var(--line);border-radius:16px;padding:18px}.notification-options{display:grid;gap:12px;grid-template-columns:repeat(2,minmax(0,1fr))}.appearance-options{display:grid;gap:16px;grid-template-columns:repeat(2,minmax(0,1fr))}.notification-options legend,.appearance-options legend{padding:0 8px}.check{align-items:center;background:var(--syn-bg-card);border:1px solid var(--line);border-radius:12px;display:flex;gap:10px;min-height:48px;padding:12px}.check input{height:18px;width:18px}.form-actions{display:flex;justify-content:flex-end}.form-actions button{border-radius:999px;min-width:170px}.floating-message{margin:0}.error{overflow-wrap:anywhere}
    .profile-page{gap:28px}.profile-grid{gap:0}.avatar-panel,.profile-settings{background:transparent;border:0;border-radius:0}.avatar-panel{border-right:1px solid var(--line);padding-left:0}.notification-options,.appearance-options{border:0;border-radius:0;border-top:1px solid var(--line);padding:18px 0 0}.check{background:transparent;border:0;border-radius:0;padding-left:0}.avatar-actions:focus-within .upload-button{outline:3px solid color-mix(in srgb,var(--syn-primary) 34%,transparent);outline-offset:3px}
    @media(max-width:900px){.profile-grid{grid-template-columns:1fr}.avatar-panel{border-bottom:1px solid var(--line);border-right:0;grid-template-columns:auto minmax(0,1fr);justify-items:start;padding:0 0 28px;text-align:left}.avatar-stage{grid-row:1/3;height:140px;margin:0 24px 0 0;width:140px}.avatar-frame{height:116px;width:116px}.avatar-fallback{font-size:3.2rem}.avatar-actions{grid-column:1/-1;grid-template-columns:1fr 1fr}}
    @media(max-width:600px){.profile-page{border-radius:20px;padding:18px}.avatar-panel{display:grid;grid-template-columns:1fr;justify-items:center;text-align:center}.avatar-stage{grid-row:auto;margin:0 0 14px}.avatar-actions{grid-template-columns:1fr}.profile-settings form,.notification-options,.appearance-options{grid-template-columns:1fr}.form-actions button{width:100%}}
  `]
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
    in_app: [true],
    density: ['comfortable' as 'comfortable' | 'compact'],
    font_scale: ['normal' as 'small' | 'normal' | 'large']
  });

  constructor() {
    effect(() => {
      const profile = this.session.profile();
      if (profile) {
        this.form.reset({
          display_name: profile.display_name,
          locale: isSupportedLocale(profile.locale) ? profile.locale : 'pt-BR',
          timezone: profile.timezone,
          ...profile.notifications,
          ...profile.appearance
        });
        if (profile.avatar && profile.avatar.sha256 !== this.loadedAvatarSha) {
          this.loadAvatar(profile.avatar.sha256);
        } else if (!profile.avatar) {
          untracked(() => this.clearAvatar());
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
      notifications: { email: value.email, in_app: value.in_app },
      appearance: { density: value.density, font_scale: value.font_scale }
    }).pipe(finalize(() => this.busy.set(false))).subscribe({
      next: () => this.message.set(this.i18n.t('profile.saved')),
      error: () => this.error.set(true)
    });
  }

  selectAvatar(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.clearAvatar();
    this.avatarUrl.set(URL.createObjectURL(file));
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
