import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { AdminUser, EffectivePermission, UserEmail } from './admin.models';
import { AdminService } from './admin.service';
import { adminFailureKey } from './admin-ui';
import { AdminAssociationPanelComponent } from './admin-association-panel.component';

@Component({
  selector: 'syn-admin-user-editor',
  imports: [AdminAssociationPanelComponent, FormsModule, RouterLink],
  templateUrl: './admin-user-editor.component.html',
  styleUrl: './admin.component.css'
})
export class AdminUserEditorComponent {
  readonly i18n = inject(I18nService);
  private readonly api = inject(AdminService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly id = this.route.snapshot.paramMap.get('userId');
  readonly loading = signal(!!this.id);
  readonly busy = signal(false);
  readonly user = signal<AdminUser | null>(null);
  readonly failure = signal<ApiFailure | null>(null);
  readonly formError = signal<TranslationKey | null>(null);
  readonly effective = signal<EffectivePermission[]>([]);
  readonly effectiveLoading = signal(false);
  readonly effectiveFailure = signal<ApiFailure | null>(null);
  displayName = '';
  status: 'pending' | 'active' = 'active';
  emails: UserEmail[] = [{ email: '', is_primary: true, is_verified: false }];
  reason = '';

  constructor() { if (this.id) this.reload(); }

  reload(): void {
    if (!this.id) return;
    this.loading.set(true);
    this.failure.set(null);
    this.api.user(this.id).subscribe({
      next: (user) => { this.accept(user); this.loading.set(false); this.loadEffective(); },
      error: (failure: ApiFailure) => { this.failure.set(failure); this.loading.set(false); }
    });
  }

  addEmail(): void {
    if (this.emails.length < 20) this.emails.push({ email: '', is_primary: false, is_verified: false });
  }
  removeEmail(index: number): void {
    if (this.emails.length <= 1) return;
    const wasPrimary = this.emails[index].is_primary;
    this.emails.splice(index, 1);
    if (wasPrimary) this.setPrimary(0);
  }
  setPrimary(index: number): void { this.emails.forEach((item, position) => item.is_primary = position === index); }

  save(event: Event): void {
    event.preventDefault();
    this.formError.set(null); this.failure.set(null);
    if (!this.valid()) return;
    const emails = this.emails.map((item) => ({ ...item, email: item.email.trim() }));
    this.busy.set(true);
    const request = this.id && this.user()
      ? this.api.updateUser(this.id, { version: this.user()!.version, display_name: this.displayName.trim(), emails, reason: this.reason.trim() })
      : this.api.createUser({ display_name: this.displayName.trim(), status: this.status, emails, reason: this.reason.trim() });
    request.subscribe({
      next: (user) => {
        this.busy.set(false);
        this.reason = '';
        if (this.id) this.accept(user);
        else void this.router.navigate(['/admin/users', user.id]);
      },
      error: (failure: ApiFailure) => { this.busy.set(false); this.failure.set(failure); }
    });
  }

  changeStatus(action: 'block' | 'unblock' | 'deactivate' | 'reactivate'): void {
    if (!this.id || !this.user() || this.busy()) return;
    this.formError.set(null); this.failure.set(null);
    if (this.reason.trim().length < 3) { this.formError.set('adminUi.reasonRequired'); return; }
    if ((action === 'block' || action === 'deactivate') && !window.confirm(this.i18n.t('adminUi.confirmStatus'))) return;
    this.busy.set(true);
    this.api.changeUserStatus(this.id, action, this.user()!.version, this.reason.trim()).subscribe({
      next: (user) => { this.accept(user); this.reason = ''; this.busy.set(false); },
      error: (failure: ApiFailure) => { this.busy.set(false); this.failure.set(failure); }
    });
  }

  failureKey(): TranslationKey { return adminFailureKey(this.failure()); }
  effectiveFailureKey(): TranslationKey { return adminFailureKey(this.effectiveFailure()); }
  formErrorMessage(): string { return this.i18n.t(this.formError() ?? 'adminUi.error'); }
  statusLabel(status: AdminUser['status']): string {
    const keys = { pending: 'userStatus.pending', active: 'userStatus.active', blocked: 'userStatus.blocked', inactive: 'userStatus.inactive' } as const;
    return this.i18n.t(keys[status]);
  }
  loadEffective(): void {
    if (!this.id) return;
    this.effectiveLoading.set(true); this.effectiveFailure.set(null);
    this.api.effectivePermissions(this.id).subscribe({
      next: (result) => { this.effective.set(result.permissions); this.effectiveLoading.set(false); },
      error: (failure: ApiFailure) => { this.effectiveFailure.set(failure); this.effectiveLoading.set(false); }
    });
  }
  sourceLabel(source: EffectivePermission['source']): string {
    const keys = { direct: 'adminUi.direct', role: 'adminUi.viaRole', group: 'adminUi.viaGroup' } as const;
    return this.i18n.t(keys[source]);
  }
  private accept(user: AdminUser): void {
    this.user.set(user);
    this.displayName = user.display_name;
    this.emails = user.emails.map((email) => ({ ...email }));
  }
  private valid(): boolean {
    if (!this.displayName.trim() || !this.emails.length || this.emails.some((item) => !item.email.trim())) {
      this.formError.set('adminUi.required'); return false;
    }
    if (this.reason.trim().length < 3) { this.formError.set('adminUi.reasonRequired'); return false; }
    const normalized = this.emails.map((item) => item.email.trim().toLowerCase());
    if (new Set(normalized).size !== normalized.length) { this.formError.set('adminUi.duplicateEmail'); return false; }
    return true;
  }
}
