import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Observable } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { AdminGroup, AdminRole } from './admin.models';
import { AdminService } from './admin.service';
import { adminFailureKey } from './admin-ui';
import { AdminAssociationPanelComponent } from './admin-association-panel.component';

@Component({
  selector: 'syn-admin-access-editor',
  imports: [AdminAssociationPanelComponent, FormsModule, RouterLink],
  templateUrl: './admin-access-editor.component.html',
  styleUrl: './admin.component.css'
})
export class AdminAccessEditorComponent {
  readonly i18n = inject(I18nService);
  private readonly api = inject(AdminService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly kind = this.route.snapshot.data['kind'] as 'groups' | 'roles';
  readonly id = this.route.snapshot.paramMap.get(this.kind === 'groups' ? 'groupId' : 'roleId');
  readonly loading = signal(!!this.id);
  readonly busy = signal(false);
  readonly item = signal<AdminGroup | AdminRole | null>(null);
  readonly failure = signal<ApiFailure | null>(null);
  readonly formError = signal<TranslationKey | null>(null);
  name = '';
  detail = '';
  reason = '';

  constructor() { if (this.id) this.reload(); }

  reload(): void {
    if (!this.id) return;
    this.loading.set(true); this.failure.set(null);
    const request: Observable<AdminGroup | AdminRole> = this.kind === 'groups' ? this.api.group(this.id) : this.api.role(this.id);
    request.subscribe({
      next: (item) => { this.accept(item); this.loading.set(false); },
      error: (failure: ApiFailure) => { this.failure.set(failure); this.loading.set(false); }
    });
  }

  save(event: Event): void {
    event.preventDefault(); this.formError.set(null); this.failure.set(null);
    if (!this.name.trim() || this.reason.trim().length < 3 || (this.kind === 'roles' && this.id && !this.detail.trim())) {
      this.formError.set('adminUi.required'); return;
    }
    const current = this.item();
    if (this.kind === 'groups' && this.id && current && 'external_reference' in current && current.external_reference && !this.detail.trim()) {
      this.formError.set('adminUi.referenceCannotClear'); return;
    }
    this.busy.set(true);
    if (this.kind === 'groups') {
      const request = this.id && this.item()
        ? this.api.updateGroup(this.id, { version: this.item()!.version, group_name: this.name.trim(), external_reference: this.detail.trim() || null, reason: this.reason.trim() })
        : this.api.createGroup({ group_name: this.name.trim(), external_reference: this.detail.trim() || null, reason: this.reason.trim() });
      request.subscribe({ next: (item) => this.saved(item), error: (failure: ApiFailure) => this.failed(failure) });
    } else {
      const request = this.id && this.item()
        ? this.api.updateRole(this.id, { version: this.item()!.version, description: this.detail.trim(), reason: this.reason.trim() })
        : this.api.createRole({ role_key: this.name.trim(), description: this.detail.trim() || null, reason: this.reason.trim() });
      request.subscribe({ next: (item) => this.saved(item), error: (failure: ApiFailure) => this.failed(failure) });
    }
  }

  changeStatus(): void {
    if (!this.id || !this.item() || this.busy()) return;
    this.formError.set(null); this.failure.set(null);
    if (this.reason.trim().length < 3) { this.formError.set('adminUi.reasonRequired'); return; }
    const action = this.item()!.is_active ? 'deactivate' : 'activate';
    if (action === 'deactivate' && !window.confirm(this.i18n.t('adminUi.confirmStatus'))) return;
    this.busy.set(true);
    const request: Observable<AdminGroup | AdminRole> = this.kind === 'groups'
      ? this.api.changeGroupStatus(this.id, action, this.item()!.version, this.reason.trim())
      : this.api.changeRoleStatus(this.id, action, this.item()!.version, this.reason.trim());
    request.subscribe({ next: (item) => this.saved(item), error: (failure: ApiFailure) => this.failed(failure) });
  }

  title(): string { return this.i18n.t(this.kind === 'groups' ? (this.id ? 'adminUi.groupDetail' : 'adminUi.newGroup') : (this.id ? 'adminUi.roleDetail' : 'adminUi.newRole')); }
  nameLabel(): string { return this.i18n.t(this.kind === 'groups' ? 'adminUi.groupName' : 'adminUi.roleKey'); }
  detailLabel(): string { return this.i18n.t(this.kind === 'groups' ? 'adminUi.externalReference' : 'adminUi.description'); }
  failureKey(): TranslationKey { return adminFailureKey(this.failure()); }
  formErrorMessage(): string { return this.i18n.t(this.formError() ?? 'adminUi.error'); }

  private accept(item: AdminGroup | AdminRole): void {
    this.item.set(item);
    this.name = 'group_name' in item ? item.group_name : item.role_key;
    this.detail = ('external_reference' in item ? item.external_reference : item.description) ?? '';
  }
  private saved(item: AdminGroup | AdminRole): void {
    this.busy.set(false); this.reason = '';
    if (this.id) this.accept(item);
    else void this.router.navigate(['/admin', this.kind, item.id]);
  }
  private failed(failure: ApiFailure): void { this.busy.set(false); this.failure.set(failure); }
}
