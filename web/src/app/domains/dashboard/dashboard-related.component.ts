import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, catchError, map, of, switchMap } from 'rxjs';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { IndicatorRelatedItem, IndicatorScope } from '../../shared/api/operational.models';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { PaginationComponent, StateComponent } from '../../shared/ui/ui-kit';
import { DashboardService } from './dashboard.service';
import { ExecutionScopeFilters } from '../executions/execution.models';
import { executionUrlParams, filtersFromParams } from '../executions/execution-presentation';

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
          <h2>{{ i18n.t(view()==='current'?'dashboard.currentWorkorders':'queries.historyResults') }}</h2>
          <p>{{ i18n.t('dashboard.relatedTotal', { count: i18n.formatNumber(total()) }) }}</p>
          @if(scope(); as currentScope){<p class="scope-note">{{ currentScope.organization_ids === null ? i18n.t('dashboard.detailScopeGlobal') : i18n.t('dashboard.detailScopeCount', { count: i18n.formatNumber(currentScope.organization_ids.length) }) }}</p>}
        </div>
      </header>

      <div class="workorders-body">
        @if (hasContext()) {
          <section class="filter-context" [attr.aria-label]="i18n.t('dashboard.activeContext')">
            <span class="context-icon" aria-hidden="true"><img src="/assets/icons/filter.svg" alt=""></span>
            <div class="context-copy">
              <strong>{{ i18n.t('dashboard.activeContext') }}</strong>
              <div class="context-values">
                @if (filters.organizationId) {
                  <span><small>{{ i18n.t('dashboard.organization') }}</small><b class="technical">{{ filters.organizationId }}</b></span>
                }
                @if (filters.dateFrom || filters.dateTo) {
                  <span><small>{{ i18n.t('dashboard.period') }}</small><b>{{ filterDate(filters.dateFrom) }} – {{ filterDate(filters.dateTo) }}</b></span>
                }
                @if (filters.source) { <span><small>{{ i18n.t('executions.source') }}</small><b>{{ filters.source }}</b></span> }
                @if (filters.fileType) { <span><small>{{ i18n.t('executions.fileType') }}</small><b>{{ filters.fileType }}</b></span> }
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
            @for (item of items(); track item.snapshot_id ?? item.identifier) {
              <a class="workorder-row" [routerLink]="['/workorders', item.identifier]" [queryParams]="{ from: currentUrl(), execution_id: item.execution_id, organization_id: item.organization_id }">
                <span class="workorder-identity">
                  <span class="workorder-icon" aria-hidden="true"><img src="/assets/icons/production.svg" alt=""></span>
                  <span><strong class="technical">{{ item.identifier }}</strong><small>{{ item.organization_name || item.organization_id || i18n.t('common.notAvailable') }}</small></span>
                </span>
                <span class="status-column"><strong class="status-pill" [attr.data-state]="statusKind(item.status)">{{ statusLabel(item.status) }}</strong><small>{{ item.status }}</small></span>
                <span class="date-column"><strong>{{ i18n.t(item.updated_at?'queries.updatedAt':'dashboard.occurredAt') }}</strong><time [attr.datetime]="item.updated_at || item.occurred_at">{{ i18n.formatDate(item.updated_at || item.occurred_at, { dateStyle: 'medium', timeStyle: 'short' }) }}</time></span>
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
export class DashboardRelatedComponent {
  readonly i18n = inject(I18nService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly service = inject(DashboardService);
  readonly items = signal<IndicatorRelatedItem[]>([]);
  readonly loading = signal(true);
  readonly error = signal<ApiFailure['kind'] | null>(null);
  readonly page = signal(1);
  readonly view = signal<'current' | 'history'>('current');
  readonly scope = signal<IndicatorScope | null>(null);
  readonly pages = signal(0);
  readonly total = signal(0);
  readonly entity = 'workorders' as const;
  filters: ExecutionScopeFilters = {};
  get context(): Record<string, string | null> { return executionUrlParams(this.filters); }

  constructor() {
    this.route.queryParamMap.pipe(
      switchMap(params => {
        this.loading.set(true); this.error.set(null); this.items.set([]);
        this.scope.set(null); this.total.set(0); this.pages.set(0);
        this.page.set(this.positivePage(params.get('page')));
        this.view.set(params.get('view') === 'history' ? 'history' : 'current');
        try { this.filters = filtersFromParams(params, this.i18n.timezone()); }
        catch { this.filters = {}; this.error.set('validation'); this.loading.set(false); return EMPTY; }
        return this.service.getRelated(this.entity, { ...this.filters, page: this.page(), view: this.view() }).pipe(
          map(value => {
            if (value.view !== this.view() || !value.scope) throw { kind: 'unavailable' };
            return { value, failure: null };
          }),
          catchError((failure: ApiFailure) => of({ value: null, failure }))
        );
      }),
      takeUntilDestroyed()
    ).subscribe(({ value, failure }) => {
      if (value) {
        this.items.set(value.items); this.scope.set(value.scope);
        this.page.set(value.pagination.page); this.pages.set(value.pagination.pages); this.total.set(value.pagination.total);
      }
      this.error.set(failure?.kind ?? null); this.loading.set(false);
    });
  }
  hasContext(): boolean { return Object.values(this.filters).some(Boolean); }
  currentUrl(): string { return this.router.url; }
  filterDate(value: string | undefined): string {
    return value ? this.i18n.formatDate(value, { dateStyle: 'short' }) : this.i18n.t('common.notAvailable');
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
    void this.router.navigate([], { relativeTo: this.route, queryParams: { view: this.view(), page }, queryParamsHandling: 'merge' });
  }

  private positivePage(value: string | null): number {
    const page = Number(value ?? 1);
    return Number.isInteger(page) && page > 0 ? page : 1;
  }
}
