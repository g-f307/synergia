import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { Indicators } from '../../shared/api/operational.models';
import { I18nService } from '../../shared/i18n/i18n.service';
import { StateComponent } from '../../shared/ui/ui-kit';
import { SessionService } from '../../core/session.service';
import { DashboardService } from './dashboard.service';
import { ExecutionScopeFilters, ExecutionOutcome } from '../executions/execution.models';
import { ExecutionScopeComponent } from '../executions/execution-scope.component';
import { executionUrlParams, filtersFromAggregate, filtersFromParams, hasExecutionAggregate, normalizedExecutionFilters, outcomeLabel, OUTCOME_COLORS } from '../executions/execution-presentation';
import { profileInput } from '../../shared/i18n/profile-time';

type DashboardState = 'loading' | 'ready' | 'partial' | 'stale' | 'forbidden' | 'unavailable' | 'error';
type QuantityKey = keyof Indicators['quantities'];

@Component({
  selector: 'syn-dashboard',
  imports: [RouterLink, StateComponent, ExecutionScopeComponent],
  template: `
    <section class="dashboard" aria-labelledby="dashboard-title" [attr.aria-busy]="state() === 'loading'">
      <header class="page-header">
        <div>
          <h1 id="dashboard-title" class="sr-only">{{ i18n.t('navigation.dashboard') }}</h1>
          <form class="dashboard-search" role="search" (submit)="submitQuickSearch($event)">
            <img src="/assets/icons/search.svg" alt="" aria-hidden="true">
            <input type="search" [value]="quickSearchQuery()" (input)="quickSearchQuery.set($any($event.target).value)" [attr.aria-label]="i18n.t('dashboard.quickSearchPlaceholder')" [placeholder]="i18n.t('dashboard.quickSearchPlaceholder')">
            <select [value]="quickSearchType()" (change)="quickSearchType.set($any($event.target).value)" [attr.aria-label]="i18n.t('dashboard.quickSearchType')">
              <option value="workorder">Workorder</option><option value="lot">{{ i18n.t('queries.lot') }}</option><option value="serial">Serial</option>
            </select>
            <button class="sr-only" type="submit">{{ i18n.t('dashboard.quickSearchAction') }}</button>
          </form>
          @if (data()?.generated_at) { <p class="updated">{{ i18n.t('dashboard.updatedAt') }} {{ i18n.formatDate(data()!.generated_at, { dateStyle: 'short', timeStyle: 'short' }) }}</p> }
        </div>
        <button type="button" class="secondary refresh" (click)="load()" [disabled]="refreshing()"><img src="/assets/icons/refresh.svg" alt="" aria-hidden="true">{{ i18n.t('dashboard.refresh') }}</button>
      </header>

      <div class="dashboard-surface">
        <details class="dashboard-filters">
          <summary>{{ i18n.t('dashboard.filters') }}</summary>
          <form (submit)="applyFilters($event)">
            <label>{{ i18n.t('dashboard.organization') }}<select [value]="organizationId()" (change)="organizationId.set($any($event.target).value)"><option value="">{{ i18n.t('dashboard.allOrganizations') }}</option>@for (organization of data()?.organizations ?? []; track organization.id) {<option [value]="organization.id">{{ organization.name }} — {{ organization.code }}</option>}</select></label>
            <label>{{ i18n.t('dashboard.dateFrom') }}<input type="date" [attr.aria-invalid]="filterError()?true:null" [attr.aria-describedby]="filterError()?'dashboard-period-error':null" [value]="dateFrom()" (input)="dateFrom.set($any($event.target).value)"></label>
            <label>{{ i18n.t('dashboard.dateTo') }}<input type="date" [attr.aria-invalid]="filterError()?true:null" [attr.aria-describedby]="filterError()?'dashboard-period-error':null" [value]="dateTo()" (input)="dateTo.set($any($event.target).value)"></label>
            <label>{{ i18n.t('executions.source') }}<input [value]="source()" (input)="source.set($any($event.target).value)"></label>
            <label>{{ i18n.t('executions.fileType') }}<input [value]="fileType()" (input)="fileType.set($any($event.target).value)"></label>
            <label>{{ i18n.t('executions.scope.status') }}<select [value]="outcome()" (change)="outcome.set($any($event.target).value)"><option value="">{{ i18n.t('executions.all') }}</option>@for (value of outcomes; track value) { <option [value]="value">{{ statusLabel(value) }}</option> }</select></label>
            <div class="filter-actions"><button type="submit">{{ i18n.t('dashboard.applyFilters') }}</button><button type="button" class="secondary" (click)="clearFilters()">{{ i18n.t('dashboard.clearFilters') }}</button></div>
          </form>
        </details>
        @if (filterError()) { <p id="dashboard-period-error" class="error filter-error" role="alert">{{ filterError() }}</p> }

        @if (state() === 'loading') { <syn-state state="loading" [title]="i18n.t('dashboard.loadingTitle')" [message]="i18n.t('dashboard.loading')" /> }
        @else if (state() === 'forbidden') { <syn-state state="forbidden" [title]="i18n.t('dashboard.forbiddenTitle')" [message]="i18n.t('dashboard.forbidden')" /> }
        @else if (state() === 'unavailable') { <syn-state state="unavailable" [title]="i18n.t('dashboard.unavailableTitle')" [message]="i18n.t('dashboard.unavailable')"><button type="button" (click)="load()">{{ i18n.t('dashboard.tryAgain') }}</button></syn-state> }
        @else if (state() === 'error') { <syn-state state="error" [title]="i18n.t('dashboard.errorTitle')" [message]="i18n.t('dashboard.error')" /> }
        @else {
          @if (state() === 'stale') { <p role="status">{{ i18n.t('executions.stale') }}</p> }
          @if (refreshing()) { <p role="status">{{ i18n.t('executions.refreshing') }}</p> }
          <syn-execution-scope [summary]="data()?.execution_summary" />
          @if (isEmpty()) { <syn-state state="success" [title]="i18n.t('dashboard.emptyTitle')" [message]="i18n.t('dashboard.empty')" /> }

          <div class="metric-grid" aria-label="Indicadores operacionais">
            <article class="metric"><div class="metric-heading"><span class="metric-badge"><img src="/assets/icons/run.svg" alt="" aria-hidden="true"></span><span>{{ i18n.t('dashboard.executions') }}</span></div><strong class="indicator-value">{{ display(totalExecutions()) }}</strong><small class="indicator-detail">{{ i18n.t('dashboard.completedCount') }}: {{ display(completedExecutions()) }}</small><a routerLink="/executions" [queryParams]="executionNavigationContext()">{{ i18n.t('dashboard.viewExecutions') }}</a></article>
            <article class="metric"><div class="metric-heading"><span class="metric-badge"><img src="/assets/icons/production.svg" alt="" aria-hidden="true"></span><span>{{ i18n.t('dashboard.workorders') }}</span></div><strong class="indicator-value">{{ display(data()?.workorders?.total) }}</strong><small class="indicator-detail">{{ i18n.t('dashboard.partialReleases') }}: {{ display(data()?.workorders?.partially_released) }}</small><a routerLink="/dashboard/related/workorders" [queryParams]="navigationContext()">{{ i18n.t('dashboard.viewWorkorders') }}</a></article>
            <article class="metric"><div class="metric-heading"><span class="metric-badge"><img src="/assets/icons/queue.svg" alt="" aria-hidden="true"></span><span>{{ i18n.t('dashboard.pending') }}</span></div><strong class="indicator-value">{{ display(totalPending()) }}</strong><small class="indicator-detail">{{ i18n.t('dashboard.openCount') }}: {{ display(openPending()) }}</small><a routerLink="/pending-items" [queryParams]="{ status: 'open' }">{{ i18n.t('dashboard.viewPending') }}</a></article>
          </div>

          <div class="chart-grid">
            <section class="chart-card quantities-chart" aria-labelledby="quantities-title">
              <header><h2 id="quantities-title">{{ i18n.t('dashboard.quantities') }}</h2></header>
              <div class="quantity-bars">
                @for (item of quantityItems; track item.key) {
                  <div class="quantity-bar"><div class="bar-label"><span>{{ i18n.t(item.label) }}</span><strong>{{ display(data()?.quantities?.[item.key]) }}</strong></div><div class="bar-track"><span [style.width.%]="quantityWidth(data()?.quantities?.[item.key])" [style.background-color]="item.color"></span></div></div>
                }
              </div>
            </section>

            <section class="chart-card execution-chart" aria-labelledby="execution-chart-title">
              <header><h2 id="execution-chart-title">{{ i18n.t('dashboard.executionStatus') }}</h2></header>
              <div class="status-chart-layout">
                <div class="status-donut" role="img" [attr.aria-label]="i18n.t('dashboard.executionStatus') + ': ' + display(totalExecutions())" [style.background]="executionDonutBackground()"><span><strong>{{ display(totalExecutions()) }}</strong><small>{{ i18n.t('dashboard.executions') }}</small></span></div>
                <div class="status-legend">
                  @for (entry of executionEntries(); track entry[0]) { <div class="status-row"><i [style.background-color]="statusColor(entry[0])" aria-hidden="true"></i><span>{{ statusLabel(entry[0]) }}</span><strong>{{ entry[1] }}</strong></div> }
                </div>
              </div>
            </section>
          </div>
        }
      </div>
    </section>
  `,
  styles: [`
    :host{display:block;height:100%;min-height:0}.dashboard{--line:color-mix(in srgb,var(--syn-text) 9%,transparent);background:var(--syn-bg-card);border:1px solid var(--line);border-radius:28px;display:grid;gap:20px;grid-template-rows:auto minmax(0,1fr);height:100%;overflow:hidden;padding:clamp(20px,2.5vw,34px)}.sr-only{left:0;top:0;height:1px;margin:-1px;overflow:hidden;padding:0;position:absolute;width:1px;clip:rect(0,0,0,0);white-space:nowrap}.page-header{align-items:center;margin:0}.updated{color:var(--syn-text-secondary);font-size:.78rem;margin:0}.refresh{background:var(--syn-bg-card);border-radius:999px;color:var(--syn-text);gap:8px}.refresh img{height:18px;width:18px}.dashboard-surface{display:grid;gap:18px;min-height:0;overflow-x:hidden;overflow-y:auto;padding-right:4px;scrollbar-gutter:stable}.dashboard-filters{background:var(--syn-bg);border:1px solid var(--line);border-radius:14px;padding:0 16px}.dashboard-filters summary{cursor:pointer;font-size:.875rem;font-weight:600;padding:13px 0}.dashboard-filters form{align-items:end;border-top:1px solid var(--line);display:grid;gap:12px;grid-template-columns:1.5fr 1fr 1fr auto;padding:16px 0}.filter-actions{display:flex;gap:8px}.filter-actions button{border-radius:999px}.filter-error{grid-column:1/-1;margin:0}.metric-grid{border:1px solid var(--line);border-radius:18px;display:grid;grid-template-columns:repeat(3,1fr);overflow:hidden}.metric{display:grid;gap:7px;min-height:154px;padding:20px 24px}.metric+.metric{border-left:1px solid var(--line)}.metric-heading{align-items:center;color:var(--syn-text-secondary);display:flex;font-size:.82rem;gap:10px}.metric-badge{align-items:center;background:var(--syn-primary-light);border:1px solid color-mix(in srgb,var(--syn-primary) 16%,transparent);border-radius:11px;display:inline-flex;height:36px;justify-content:center;width:36px}.metric-badge img{filter:none;height:18px;width:18px}.metric small{color:var(--syn-text-secondary);font-size:.82rem}.metric strong{font-family:LGEIHeadline,sans-serif;font-size:2.3rem;line-height:1}.metric a{color:var(--syn-link);font-size:.82rem;font-weight:600;margin-top:auto;text-decoration:none}.chart-grid{display:grid;gap:18px;grid-template-columns:1.25fr 1fr}.chart-card{border:1px solid var(--line);border-radius:18px;padding:22px}.chart-card h2{font-size:1rem;margin:0}.chart-card header{margin-bottom:24px}.quantity-bars{display:grid;gap:17px}.quantity-bar{display:grid;gap:7px}.bar-label{display:flex;justify-content:space-between}.bar-label span,.status-row>span{color:var(--syn-text-secondary);font-size:.8rem}.bar-track{background:var(--syn-bg);border-radius:999px;height:10px;overflow:hidden}.bar-track span{border-radius:inherit;display:block;height:100%;min-width:2px}.status-chart-layout{align-items:center;display:grid;gap:26px;grid-template-columns:148px minmax(0,1fr)}.status-donut{align-items:center;aspect-ratio:1;border-radius:50%;display:flex;justify-content:center;position:relative;width:148px}.status-donut::after{background:var(--syn-bg-card);border-radius:50%;content:"";inset:22px;position:absolute}.status-donut>span{display:grid;position:relative;text-align:center;z-index:1}.status-donut strong{font-family:LGEIHeadline,sans-serif;font-size:1.8rem;line-height:1}.status-donut small{color:var(--syn-text-secondary);font-size:.72rem;margin-top:5px}.status-legend{display:grid;gap:12px}.status-row{align-items:center;display:grid;gap:9px;grid-template-columns:10px minmax(80px,1fr) 30px}.status-row i{border-radius:50%;height:9px;width:9px}.status-row strong{text-align:right}.partial{margin:0}
    .page-header{align-items:flex-start}.refresh{min-height:42px}
    .page-header>div{display:grid;gap:8px;min-width:min(100%,380px)}.dashboard-search{align-items:center;background:var(--syn-bg);border:1px solid transparent;border-radius:999px;display:grid;grid-template-columns:20px minmax(0,1fr) auto;max-width:380px;min-height:42px;padding:4px 8px 4px 14px;transition:border-color var(--syn-transition),box-shadow var(--syn-transition)}.dashboard-search:focus-within{border-color:color-mix(in srgb,var(--syn-primary) 38%,transparent);box-shadow:0 0 0 3px color-mix(in srgb,var(--syn-primary) 10%,transparent)}.dashboard-search>img{height:17px;width:17px}.dashboard-search input,.dashboard-search select{background:transparent;border:0;color:var(--syn-text);min-height:32px;outline:0}.dashboard-search input{min-width:0;padding:0 6px}.dashboard-search input::-webkit-search-cancel-button{cursor:pointer}.dashboard-search select{border-left:1px solid var(--line);border-radius:0;font-size:.72rem;padding:0 5px 0 9px}.dashboard-search input::placeholder{color:var(--syn-text-secondary)}
    .dashboard-surface{align-content:start;grid-auto-rows:max-content}
    @media(max-width:900px){.dashboard-filters form{grid-template-columns:1fr 1fr}.chart-grid{grid-template-columns:1fr}}
    @media(max-width:440px){.status-chart-layout{grid-template-columns:1fr}.status-donut{margin-inline:auto}}
    @media(max-width:600px){.dashboard{border-radius:20px;padding:18px}.page-header{align-items:stretch}.page-header button{width:100%}.metric-grid{grid-template-columns:1fr}.metric+.metric{border-left:0;border-top:1px solid var(--line)}.dashboard-filters form{grid-template-columns:1fr}.filter-actions{display:grid;grid-template-columns:1fr 1fr}.chart-card{padding:18px}}
  `]
})
export class DashboardComponent implements OnInit, OnDestroy {
  readonly i18n = inject(I18nService);
  private readonly service = inject(DashboardService);
  private readonly session = inject(SessionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly state = signal<DashboardState>('loading');
  readonly data = signal<Indicators | null>(null);
  readonly receivedAt = signal<Date | null>(null);
  readonly organizationId = signal('');
  readonly dateFrom = signal('');
  readonly dateTo = signal('');
  readonly filterError = signal('');
  readonly quickSearchQuery = signal('');
  readonly quickSearchType = signal<'workorder' | 'lot' | 'serial'>('workorder');
  private request?: Subscription;
  private routeRequest?: Subscription;
  private requested: ExecutionScopeFilters = {};
  private requestKey = '';
  private invalidRoute = false;
  readonly source = signal('');
  readonly fileType = signal('');
  readonly outcome = signal<ExecutionOutcome | ''>('');
  readonly refreshing = signal(false);
  readonly outcomes: ExecutionOutcome[] = ['active', 'completed', 'partial', 'skipped_duplicate', 'failed', 'cancelled', 'unknown'];
  private readonly successfulFilters = signal<ExecutionScopeFilters>({});
  readonly navigationContext = computed(() => executionUrlParams(this.successfulFilters()));
  readonly executionNavigationContext = computed(() => ({ ...this.navigationContext(), page: 1, sort: 'newest' }));
  readonly quantityItems: Array<{ key: QuantityKey; label: 'dashboard.planned' | 'dashboard.produced' | 'dashboard.received' | 'dashboard.released'; color: string }> = [
    { key: 'planned', label: 'dashboard.planned', color: '#5577b8' }, { key: 'produced', label: 'dashboard.produced', color: '#567f9f' },
    { key: 'received', label: 'dashboard.received', color: '#2e8c87' }, { key: 'released', label: 'dashboard.released', color: '#39805f' }
  ];
  readonly totalExecutions = computed(() => this.data()?.execution_summary?.total);
  readonly completedExecutions = computed(() => this.data()?.execution_summary?.by_outcome?.completed);
  readonly totalPending = computed(() => this.sum(this.data()?.pending_items));
  readonly openPending = computed(() => {
    const pendingItems = this.data()?.pending_items;
    return pendingItems ? (pendingItems['open'] ?? 0) : undefined;
  });
  readonly executionEntries = computed<Array<[ExecutionOutcome, number]>>(() => {
    const summary = this.data()?.execution_summary;
    return hasExecutionAggregate(summary) ? this.outcomes.map(value => [value, summary.by_outcome[value]]) : [];
  });
  readonly executionDonutBackground = computed(() => {
    const entries = this.executionEntries();
    const total = entries.reduce((sum, entry) => sum + entry[1], 0);
    if (total === 0) return 'conic-gradient(#d7d9de 0 100%)';
    let start = 0;
    const segments = entries.map(([status, count]) => {
      const end = start + (count / total) * 100;
      const segment = `${this.statusColor(status)} ${start}% ${end}%`;
      start = end;
      return segment;
    });
    return `conic-gradient(${segments.join(', ')})`;
  });
  readonly isEmpty = computed(() => this.state() === 'ready' && [this.totalExecutions(), this.totalPending(), this.data()?.workorders?.total].every((value) => value === 0));
  readonly scopeDescription = computed(() => {
    const permission = this.session.profile()?.permissions.find((item) => item.key === 'dashboard.read');
    if (permission?.organizations === null) return this.i18n.t('dashboard.scopeGlobal');
    const count = permission?.organizations?.length ?? 0;
    return this.i18n.t('dashboard.scopeOrganizations', { count: this.i18n.formatNumber(count) });
  });

  ngOnInit(): void {
    this.routeRequest = this.route.queryParamMap.subscribe(params => {
      try {
        const filters = filtersFromParams(params, this.i18n.timezone());
        this.invalidRoute = false; this.filterError.set('');
        if (JSON.stringify(executionUrlParams(filters)) === this.requestKey) return;
        this.organizationId.set(filters.organizationId ?? '');
        this.dateFrom.set(profileInput(filters.dateFrom, this.i18n.timezone(), true));
        this.dateTo.set(profileInput(filters.dateTo, this.i18n.timezone(), true));
        this.source.set(filters.source ?? ''); this.fileType.set(filters.fileType ?? ''); this.outcome.set(filters.outcome ?? '');
        this.load(filters);
      } catch { this.invalidRoute = true; this.requestKey = ''; this.request?.unsubscribe(); this.refreshing.set(false); this.filterError.set(this.i18n.t('executions.invalidPeriod')); this.state.set(this.data() ? 'stale' : 'error'); }
    });
  }
  ngOnDestroy(): void { this.request?.unsubscribe(); this.routeRequest?.unsubscribe(); }
  submitQuickSearch(event: Event): void {
    event.preventDefault();
    const query = this.quickSearchQuery().trim();
    if (!query) return;
    void this.router.navigate(['/search'], {
      queryParams: { type: this.quickSearchType(), query, page: 1, pageSize: 25, sort: 'updated_desc' }
    });
  }
  applyFilters(event: Event): void {
    event.preventDefault();
    try {
      const period = (bound: 'start' | 'end') => {
        const old = bound === 'start' ? this.requested.dateFrom : this.requested.dateTo;
        const value = bound === 'start' ? this.dateFrom() : this.dateTo();
        return value === profileInput(old, this.i18n.timezone(), true) ? old : value;
      };
      const filters = normalizedExecutionFilters({ ...this.requested, organizationId: this.organizationId(),
        source: this.source(), fileType: this.fileType(), outcome: this.outcome() || undefined,
        lifecycle: (this.outcome() || undefined) !== this.requested.outcome ? undefined : this.requested.lifecycle,
        dateFrom: period('start'), dateTo: period('end') }, this.i18n.timezone());
      this.invalidRoute = false; this.filterError.set(''); this.load(filters);
    } catch { this.filterError.set(this.i18n.t('executions.invalidPeriod')); }
  }
  clearFilters(): void {
    this.organizationId.set(''); this.dateFrom.set(''); this.dateTo.set(''); this.filterError.set('');
    this.invalidRoute = false; this.source.set(''); this.fileType.set(''); this.outcome.set(''); this.load({});
  }
  quantityWidth(value: number | null | undefined): number {
    if (value === null || value === undefined) return 0;
    const values = Object.values(this.data()?.quantities ?? {}).filter((item): item is number => typeof item === 'number');
    const maximum = Math.max(...values, 0);
    return maximum > 0 ? (value / maximum) * 100 : 0;
  }
  distributionWidth(value: number, entries: Array<[string, number]>): number {
    const maximum = Math.max(...entries.map((entry) => entry[1]), 0);
    return maximum > 0 ? (value / maximum) * 100 : 0;
  }
  statusLabel(value: string): string {
    return this.i18n.t(outcomeLabel(value));
  }
  statusColor(value: string): string {
    return OUTCOME_COLORS[value as ExecutionOutcome] ?? OUTCOME_COLORS.unknown;
  }
  load(filters: ExecutionScopeFilters = this.requested): void {
    if (this.invalidRoute) return;
    this.request?.unsubscribe();
    this.requested = filters; this.requestKey = JSON.stringify(executionUrlParams(filters));
    this.refreshing.set(true);
    if (!this.data()) this.state.set('loading');
    this.request = this.service.getIndicators(filters).subscribe({
      next: (data) => {
        this.data.set(data);
        this.receivedAt.set(new Date());
        const effective = hasExecutionAggregate(data.execution_summary) ? filtersFromAggregate(data.execution_summary) : filters;
        this.successfulFilters.set(effective); this.requestKey = JSON.stringify(executionUrlParams(effective));
        if (!this.router.getCurrentNavigation()) void this.router.navigate([], { relativeTo: this.route, queryParams: executionUrlParams(effective), replaceUrl: true });
        this.state.set(this.isPartial(data) ? 'partial' : 'ready');
        this.refreshing.set(false);
      },
      error: (failure: ApiFailure) => {
        if (failure.kind === 'forbidden' || failure.kind === 'unauthorized') {
          this.data.set(null); this.receivedAt.set(null); this.state.set('forbidden');
        } else this.state.set(this.data() ? 'stale' : failure.kind === 'unavailable' ? 'unavailable' : 'error');
        this.refreshing.set(false);
      }
    });
  }
  display(value: number | null | undefined): string { return value == null ? this.i18n.t('dashboard.absent') : this.i18n.formatNumber(value); }
  private sum(group: Record<string, number> | null | undefined): number | undefined { return group ? Object.values(group).reduce((total, value) => total + value, 0) : undefined; }
  private isPartial(data: Indicators): boolean {
    return !hasExecutionAggregate(data.execution_summary) || data.workorders?.total == null || data.workorders?.partially_released == null || this.quantityItems.some((item) => data.quantities?.[item.key] == null);
  }
}
