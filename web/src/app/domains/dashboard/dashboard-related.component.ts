import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { PaginationComponent, StateComponent } from '../../shared/ui/ui-kit';
import { DashboardService } from './dashboard.service';

interface RelatedWorkorder {
  identifier: string;
  status: string;
  occurred_at: string;
}

@Component({
  imports: [RouterLink, PaginationComponent, StateComponent],
  template: `
    <section class="workorders-page" aria-labelledby="workorders-title">
      <h1 id="workorders-title" class="sr-only">{{ i18n.t('dashboard.workorders') }}</h1>

      <header class="results-heading">
        <a class="back-link" routerLink="/dashboard" [queryParams]="context">
          <span aria-hidden="true">←</span>{{ i18n.t('dashboard.back') }}
        </a>
        <div>
          <h2>{{ i18n.t('dashboard.relatedRecords') }}</h2>
          <p>{{ i18n.t('dashboard.relatedTotal', { count: i18n.formatNumber(total()) }) }}</p>
        </div>
      </header>

      <div class="workorders-body">
        @if (hasContext()) {
          <section class="filter-context" [attr.aria-label]="i18n.t('dashboard.activeContext')">
            <span class="context-icon" aria-hidden="true"><img src="/assets/icons/filter.svg" alt=""></span>
            <div class="context-copy">
              <strong>{{ i18n.t('dashboard.activeContext') }}</strong>
              <div class="context-values">
                @if (context.organization) {
                  <span><small>{{ i18n.t('dashboard.organization') }}</small><b class="technical">{{ context.organization }}</b></span>
                }
                @if (context.dateFrom || context.dateTo) {
                  <span><small>{{ i18n.t('dashboard.period') }}</small><b>{{ filterDate(context.dateFrom) }} – {{ filterDate(context.dateTo) }}</b></span>
                }
              </div>
            </div>
          </section>
        }

        @if (loading()) {
          <syn-state state="loading" [title]="i18n.t('dashboard.loadingTitle')" [message]="i18n.t('dashboard.loading')" />
        } @else if (error() === 'forbidden') {
          <syn-state state="forbidden" [title]="i18n.t('dashboard.forbiddenTitle')" [message]="i18n.t('dashboard.forbidden')" />
        } @else if (error() === 'unavailable') {
          <syn-state state="unavailable" [title]="i18n.t('dashboard.unavailableTitle')" [message]="i18n.t('dashboard.unavailable')" />
        } @else if (error()) {
          <syn-state state="error" [title]="i18n.t('dashboard.errorTitle')" [message]="i18n.t('dashboard.error')" />
        } @else if (!items().length) {
          <syn-state state="success" [title]="i18n.t('dashboard.emptyTitle')" [message]="i18n.t('dashboard.empty')" />
        } @else {
          <div class="workorder-list">
            @for (item of items(); track item.identifier) {
              <a class="workorder-row" [routerLink]="['/workorders', item.identifier]" [queryParams]="{ from: currentUrl() }">
                <span class="workorder-identity">
                  <span class="workorder-icon" aria-hidden="true"><img src="/assets/icons/production.svg" alt=""></span>
                  <span><strong class="technical">{{ item.identifier }}</strong><small>Workorder</small></span>
                </span>
                <span class="status-column"><strong class="status-pill" [attr.data-state]="statusKind(item.status)">{{ statusLabel(item.status) }}</strong><small>{{ item.status }}</small></span>
                <span class="date-column"><strong>{{ i18n.t('dashboard.occurredAt') }}</strong><time [attr.datetime]="item.occurred_at">{{ i18n.formatDate(item.occurred_at, { dateStyle: 'medium', timeStyle: 'short' }) }}</time></span>
                <span class="row-chevron" aria-hidden="true">›</span>
              </a>
            }
          </div>
          @if (pages()) {
            <syn-pagination [page]="page()" [pages]="pages()" (pageChange)="changePage($event)" />
          }
        }
      </div>
    </section>
  `,
  styleUrl: './dashboard-related.component.css'
})
export class DashboardRelatedComponent implements OnInit {
  readonly i18n = inject(I18nService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly service = inject(DashboardService);
  readonly items = signal<RelatedWorkorder[]>([]);
  readonly loading = signal(true);
  readonly error = signal<ApiFailure['kind'] | null>(null);
  readonly page = signal(this.positivePage(this.route.snapshot.queryParamMap.get('page')));
  readonly pages = signal(0);
  readonly total = signal(0);
  readonly entity = 'workorders' as const;
  readonly context = {
    organization: this.route.snapshot.queryParamMap.get('organization'),
    dateFrom: this.route.snapshot.queryParamMap.get('dateFrom'),
    dateTo: this.route.snapshot.queryParamMap.get('dateTo')
  };

  ngOnInit(): void { this.load(); }
  hasContext(): boolean { return Boolean(this.context.organization || this.context.dateFrom || this.context.dateTo); }
  currentUrl(): string { return this.router.url; }
  filterDate(value: string | null): string {
    return value ? this.i18n.formatDate(`${value}T12:00:00`, { dateStyle: 'short' }) : this.i18n.t('common.notAvailable');
  }
  statusKind(status: string): string {
    if (status === 'consolidated' || status === 'validated') return 'success';
    if (status === 'failed') return 'error';
    return 'pending';
  }
  statusLabel(status: string): string {
    const labels: Record<string, 'dashboard.workorderStatus.consolidated' | 'dashboard.workorderStatus.validated' | 'dashboard.workorderStatus.pending' | 'dashboard.workorderStatus.failed'> = {
      consolidated: 'dashboard.workorderStatus.consolidated',
      validated: 'dashboard.workorderStatus.validated',
      pending: 'dashboard.workorderStatus.pending',
      failed: 'dashboard.workorderStatus.failed'
    };
    return labels[status] ? this.i18n.t(labels[status]) : status;
  }
  changePage(page: number): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { page }, queryParamsHandling: 'merge' })
      .then(() => { this.page.set(page); this.load(); });
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.service.getRelated(this.entity, {
      organizationId: this.context.organization ?? '',
      dateFrom: this.context.dateFrom ?? '',
      dateTo: this.context.dateTo ?? '',
      page: this.page()
    }).subscribe({
      next: (value) => {
        this.items.set(value.items);
        this.page.set(value.pagination.page);
        this.pages.set(value.pagination.pages);
        this.total.set(value.pagination.total);
        this.loading.set(false);
      },
      error: (failure: ApiFailure) => { this.error.set(failure.kind); this.loading.set(false); }
    });
  }
  private positivePage(value: string | null): number {
    const page = Number(value ?? 1);
    return Number.isInteger(page) && page > 0 ? page : 1;
  }
}
