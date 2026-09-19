import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
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
  imports: [RouterLink],
  templateUrl: './admin-access-list.component.html',
  styleUrl: './admin.component.css'
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
  failureKey(): TranslationKey { return adminFailureKey(this.failure()); }
  retry(): void { this.refreshRequested.next(); }
  changePage(page: number): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { page } });
  }
  private load(page: number): Observable<AdminPage<AdminGroup | AdminRole>> {
    return this.kind === 'groups' ? this.api.groups(page) : this.api.roles(page);
  }
}
