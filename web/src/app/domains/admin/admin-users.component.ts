import { Component, HostListener, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { catchError, map, of, startWith, Subject, switchMap, tap } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { AdminPage, AdminUser, UserFilters, UserStatus } from './admin.models';
import { AdminService } from './admin.service';
import { adminFailureKey, positivePage } from './admin-ui';

@Component({
  selector: 'syn-admin-users',
  imports: [FormsModule, RouterLink],
  templateUrl: './admin-users.component.html',
  styleUrl: './admin.component.css',
  host: { class: 'admin-route' }
})
export class AdminUsersComponent {
  readonly i18n = inject(I18nService);
  private readonly api = inject(AdminService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly refreshRequested = new Subject<void>();
  readonly loading = signal(true);
  readonly result = signal<AdminPage<AdminUser> | null>(null);
  readonly failure = signal<ApiFailure | null>(null);
  readonly lifecycleTarget = signal<AdminUser | null>(null);
  readonly lifecycleError = signal<TranslationKey | null>(null);
  readonly lifecycleBusy = signal(false);
  filters: UserFilters = {};
  lifecycleReason = '';
  readonly statuses: UserStatus[] = ['pending', 'active', 'blocked', 'inactive'];

  constructor() {
    this.route.queryParamMap.pipe(
      switchMap((params) => this.refreshRequested.pipe(
        startWith(undefined),
        tap(() => {
          this.filters = {
            name: params.get('name') ?? '', email: params.get('email') ?? '',
            status: this.status(params.get('status')), group: params.get('group') ?? '',
            role: params.get('role') ?? '', organization: params.get('organization') ?? ''
          };
          this.loading.set(true);
          this.failure.set(null);
        }),
        switchMap(() => this.api.users(positivePage(params.get('page')), 25, this.filters).pipe(
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

  apply(event: Event): void { event.preventDefault(); this.navigate(1); }
  clear(): void {
    this.filters = { name: '', email: '', status: undefined, group: '', role: '', organization: '' };
    this.navigate(1);
  }
  changePage(number: number): void { this.navigate(number); }
  retry(): void { this.refreshRequested.next(); }
  statusLabel(status: UserStatus): string { return this.i18n.t(`userStatus.${status}`); }
  failureKey(): TranslationKey { return adminFailureKey(this.failure()); }
  formatDate(value: string): string { return this.i18n.formatDate(value); }

  openLifecycle(user: AdminUser): void {
    this.lifecycleTarget.set(user);
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
    const user = this.lifecycleTarget();
    if (!user || this.lifecycleBusy()) return;
    const reason = this.lifecycleReason.trim();
    if (reason.length < 3) {
      this.lifecycleError.set('adminUi.reasonRequired');
      return;
    }
    const action = user.status === 'inactive' ? 'reactivate' : 'deactivate';
    this.lifecycleError.set(null);
    this.lifecycleBusy.set(true);
    this.api.changeUserStatus(user.id, action, user.version, reason).subscribe({
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

  private navigate(page: number): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        page, name: this.filters.name?.trim() || null, email: this.filters.email?.trim() || null,
        status: this.filters.status || null, group: this.filters.group?.trim() || null,
        role: this.filters.role?.trim() || null, organization: this.filters.organization?.trim() || null
      }
    });
  }
  private status(value: string | null): UserStatus | undefined {
    return this.statuses.find((item) => item === value);
  }
}
