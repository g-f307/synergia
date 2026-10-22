import { Component, HostListener, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { catchError, map, Observable, of, startWith, Subject, switchMap, tap } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { AdminGroup, AdminPage, AdminRole } from './admin.models';
import { AdminService } from './admin.service';
import { adminFailureKey, positivePage } from './admin-ui';

@Component({
  selector: 'syn-admin-access-list',
  imports: [FormsModule, RouterLink],
  templateUrl: './admin-access-list.component.html',
  styleUrl: './admin.component.css',
  host: { class: 'admin-route' }
})
export class AdminAccessListComponent {
  readonly i18n = inject(I18nService);
  private readonly api = inject(AdminService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly refreshRequested = new Subject<void>();
  readonly kind = this.route.snapshot.data['kind'] as 'groups' | 'roles';
  readonly loading = signal(true);
  readonly result = signal<AdminPage<AdminGroup | AdminRole> | null>(null);
  readonly failure = signal<ApiFailure | null>(null);
  readonly lifecycleTarget = signal<AdminGroup | AdminRole | null>(null);
  readonly lifecycleError = signal<TranslationKey | null>(null);
  readonly lifecycleBusy = signal(false);
  lifecycleReason = '';

  constructor() {
    this.route.queryParamMap.pipe(
      switchMap((params) => this.refreshRequested.pipe(
        startWith(undefined),
        tap(() => { this.loading.set(true); this.failure.set(null); }),
        switchMap(() => this.load(positivePage(params.get('page'))).pipe(
          map((value) => ({ value, failure: null })),
          catchError((failure: ApiFailure) => of({ value: null, failure }))
        ))
      )),
      takeUntilDestroyed()
    ).subscribe(({ value, failure }) => {
      this.result.set(value);
      this.failure.set(failure);
      this.loading.set(false);
    });
  }

  title(): string { return this.i18n.t(this.kind === 'groups' ? 'adminUi.groups' : 'adminUi.roles'); }
  newTitle(): string { return this.i18n.t(this.kind === 'groups' ? 'adminUi.newGroup' : 'adminUi.newRole'); }
  name(item: AdminGroup | AdminRole): string { return 'group_name' in item ? item.group_name : item.role_key; }
  detail(item: AdminGroup | AdminRole): string {
    return ('external_reference' in item ? item.external_reference : item.description) || this.i18n.t('adminUi.noDescription');
  }
  description(): string { return this.i18n.t(this.kind === 'groups' ? 'adminUi.groupsDescription' : 'adminUi.rolesDescription'); }
  formatDate(value: string): string { return this.i18n.formatDate(value); }
  failureKey(): TranslationKey { return adminFailureKey(this.failure()); }
  retry(): void { this.refreshRequested.next(); }
  changePage(page: number): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { page } });
  }
  openLifecycle(item: AdminGroup | AdminRole): void {
    this.lifecycleTarget.set(item);
    this.lifecycleReason = '';
    this.lifecycleError.set(null);
  }
  closeLifecycle(): void {
    if (this.lifecycleBusy()) return;
    this.lifecycleTarget.set(null);
    this.lifecycleReason = '';
    this.lifecycleError.set(null);
  }
  submitLifecycle(event: Event): void {
    event.preventDefault();
    const item = this.lifecycleTarget();
    if (!item || this.lifecycleBusy()) return;
    const reason = this.lifecycleReason.trim();
    if (reason.length < 3) {
      this.lifecycleError.set('adminUi.reasonRequired');
      return;
    }
    const action = item.is_active ? 'deactivate' : 'activate';
    const request: Observable<AdminGroup | AdminRole> = this.kind === 'groups'
      ? this.api.changeGroupStatus(item.id, action, item.version, reason)
      : this.api.changeRoleStatus(item.id, action, item.version, reason);
    this.lifecycleBusy.set(true);
    this.lifecycleError.set(null);
    request.subscribe({
      next: () => {
        this.lifecycleBusy.set(false);
        this.closeLifecycle();
        this.refreshRequested.next();
      },
      error: (failure: ApiFailure) => {
        this.lifecycleBusy.set(false);
        this.failure.set(failure);
        this.lifecycleTarget.set(null);
      }
    });
  }
  @HostListener('document:keydown.escape')
  closeOnEscape(): void { this.closeLifecycle(); }
  private load(page: number): Observable<AdminPage<AdminGroup | AdminRole>> {
    return this.kind === 'groups' ? this.api.groups(page) : this.api.roles(page);
  }
}
