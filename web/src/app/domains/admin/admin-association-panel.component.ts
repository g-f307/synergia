import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Observable, catchError, forkJoin, map, of } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { AdminAssociation, AdminGroup, AdminPage, AdminRole, AdminUser, AssociationKind } from './admin.models';
import { AdminService } from './admin.service';
import { adminFailureKey } from './admin-ui';

type Target = 'user' | 'group' | 'role' | 'permission';

@Component({
  selector: 'syn-admin-association-panel',
  imports: [FormsModule, RouterLink],
  templateUrl: './admin-association-panel.component.html',
  styleUrl: './admin.component.css'
})
export class AdminAssociationPanelComponent implements OnInit {
  readonly i18n = inject(I18nService);
  private readonly api = inject(AdminService);
  @Input({ required: true }) kind!: AssociationKind;
  @Input({ required: true }) side!: 'left' | 'right';
  @Input({ required: true }) entityId!: string;
  @Input({ required: true }) target!: Target;
  @Input({ required: true }) titleKey!: TranslationKey;
  @Output() changed = new EventEmitter<void>();
  readonly loading = signal(true);
  readonly result = signal<AdminPage<AdminAssociation> | null>(null);
  readonly failure = signal<ApiFailure | null>(null);
  readonly labels = signal<Record<string, string>>({});
  readonly candidateOptions = signal<{ id: string; label: string }[]>([]);
  readonly candidatePages = signal(1);
  readonly candidateFailure = signal<ApiFailure | null>(null);
  readonly organizationOptions = signal<{ id: string; label: string }[]>([]);
  readonly organizationPages = signal(1);
  readonly organizationFailure = signal<ApiFailure | null>(null);
  readonly mutationFailure = signal<ApiFailure | null>(null);
  readonly formError = signal<TranslationKey | null>(null);
  readonly busy = signal(false);
  selectedTarget = '';
  selectedOrganization = '';
  scope: 'global' | 'organization' = 'global';
  targetQuery = '';
  organizationQuery = '';
  reason = '';
  private page = 1;
  candidatePage = 1;
  organizationPage = 1;

  ngOnInit(): void { this.reload(); this.loadCandidates(); if (this.scoped()) this.loadOrganizations(); }
  reload(): void {
    this.loading.set(true); this.failure.set(null);
    const filter = this.side === 'left' ? { left_id: this.entityId } : { right_id: this.entityId };
    this.api.associations(this.kind, this.page, 25, { ...filter, active_only: true }).subscribe({
      next: (result) => {
        this.result.set(result); this.loading.set(false);
        this.loadLabels(result.items);
      },
      error: (failure: ApiFailure) => { this.failure.set(failure); this.loading.set(false); }
    });
  }
  changePage(page: number): void { this.page = page; this.reload(); }
  scoped(): boolean { return this.kind === 'user_role' || this.kind === 'group_role' || this.kind === 'user_permission'; }
  searchCandidates(event: Event): void { event.preventDefault(); this.candidatePage = 1; this.loadCandidates(); }
  searchOrganizations(event: Event): void { event.preventDefault(); this.organizationPage = 1; this.loadOrganizations(); }
  changeCandidatePage(page: number): void { this.candidatePage = page; this.loadCandidates(); }
  changeOrganizationPage(page: number): void { this.organizationPage = page; this.loadOrganizations(); }
  loadCandidates(): void {
    this.candidateFailure.set(null); this.selectedTarget = '';
    if (this.target === 'permission') {
      this.api.permissions().subscribe({
        next: (items) => { this.candidateOptions.set(items.filter((item) => item.is_active).map((item) => ({ id: item.id, label: item.permission_key }))); this.candidatePages.set(1); },
        error: (failure: ApiFailure) => this.candidateFailure.set(failure)
      });
      return;
    }
    const request: Observable<AdminPage<AdminUser | AdminGroup | AdminRole>> =
      this.target === 'user' ? this.api.users(this.candidatePage, 25, { name: this.targetQuery.trim(), status: 'active' })
      : this.target === 'group' ? this.api.groups(this.candidatePage) : this.api.roles(this.candidatePage);
    request.subscribe({
      next: (page) => {
        this.candidateOptions.set(page.items.filter((item) => 'status' in item || item.is_active).map((item) => ({
          id: item.id, label: 'display_name' in item ? item.display_name : 'group_name' in item ? item.group_name : item.role_key
        })));
        this.candidatePages.set(page.pages);
      },
      error: (failure: ApiFailure) => this.candidateFailure.set(failure)
    });
  }
  loadOrganizations(): void {
    this.organizationFailure.set(null); this.selectedOrganization = '';
    this.api.organizations(this.organizationPage, this.organizationQuery.trim()).subscribe({
      next: (page) => {
        this.organizationOptions.set(page.items.map((item) => ({ id: item.id, label: `${item.organization_code} — ${item.display_name}` })));
        this.organizationPages.set(page.pages);
      },
      error: (failure: ApiFailure) => this.organizationFailure.set(failure)
    });
  }
  grant(event: Event): void {
    event.preventDefault(); this.formError.set(null); this.mutationFailure.set(null);
    if (this.candidateFailure() || !this.selectedTarget || this.reason.trim().length < 3 ||
        (this.scoped() && this.scope === 'organization' && (this.organizationFailure() || !this.selectedOrganization))) {
      this.formError.set('adminUi.associationRequired'); return;
    }
    const leftId = this.side === 'left' ? this.entityId : this.selectedTarget;
    const rightId = this.side === 'left' ? this.selectedTarget : this.entityId;
    const organizationId = this.scoped() && this.scope === 'organization' ? this.selectedOrganization : undefined;
    this.busy.set(true);
    this.api.grant(this.kind, leftId, rightId, this.reason.trim(), organizationId).subscribe({
      next: () => { this.busy.set(false); this.reason = ''; this.selectedTarget = ''; this.reload(); this.changed.emit(); },
      error: (failure: ApiFailure) => { this.busy.set(false); this.mutationFailure.set(failure); }
    });
  }
  revoke(link: AdminAssociation): void {
    this.formError.set(null); this.mutationFailure.set(null);
    if (this.reason.trim().length < 3) { this.formError.set('adminUi.reasonRequired'); return; }
    if (!window.confirm(this.i18n.t('adminUi.confirmRevoke'))) return;
    this.busy.set(true);
    this.api.revoke(this.kind, link.left_id, link.right_id, this.reason.trim(), link.organization_id ?? undefined).subscribe({
      next: () => { this.busy.set(false); this.reason = ''; this.reload(); this.changed.emit(); },
      error: (failure: ApiFailure) => { this.busy.set(false); this.mutationFailure.set(failure); }
    });
  }
  failureKey(): TranslationKey { return adminFailureKey(this.failure()); }
  candidateFailureKey(): TranslationKey { return adminFailureKey(this.candidateFailure()); }
  organizationFailureKey(): TranslationKey { return adminFailureKey(this.organizationFailure()); }
  mutationFailureKey(): TranslationKey { return adminFailureKey(this.mutationFailure()); }
  formErrorMessage(): string { return this.i18n.t(this.formError() ?? 'adminUi.error'); }
  targetId(link: AdminAssociation): string { return this.side === 'left' ? link.right_id : link.left_id; }
  label(link: AdminAssociation): string { return this.labels()[this.targetId(link)] ?? this.targetId(link); }
  targetRoute(id: string): string[] {
    const segment = this.target === 'user' ? 'users' : this.target === 'group' ? 'groups' : 'roles';
    return ['/admin', segment, id];
  }

  private loadLabels(items: AdminAssociation[]): void {
    if (!items.length) { this.labels.set({}); return; }
    if (this.target === 'permission') {
      this.api.permissions().subscribe({
        next: (permissions) => this.labels.set(Object.fromEntries(permissions.map((item) => [item.id, item.permission_key]))),
        error: () => this.labels.set({})
      });
      return;
    }
    const requests = items.map((link): Observable<readonly [string, string]> => {
      const id = this.targetId(link);
      const detail: Observable<AdminUser | AdminGroup | AdminRole> = this.target === 'user' ? this.api.user(id) : this.target === 'group' ? this.api.group(id) : this.api.role(id);
      return detail.pipe(
        map((item): readonly [string, string] => [id, 'display_name' in item ? item.display_name : 'group_name' in item ? item.group_name : item.role_key]),
        catchError(() => of([id, id] as const))
      );
    });
    forkJoin(requests).subscribe((pairs) => this.labels.set(Object.fromEntries(pairs)));
  }
}
