import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { Indicators } from '../../shared/api/operational.models';
import { I18nService } from '../../shared/i18n/i18n.service';
import { StateComponent } from '../../shared/ui/ui-kit';
import { SessionService } from '../../core/session.service';
import { DashboardService } from './dashboard.service';

type DashboardState = 'loading' | 'ready' | 'partial' | 'forbidden' | 'unavailable' | 'error';
type QuantityKey = keyof Indicators['quantities'];

@Component({
  selector: 'syn-dashboard',
  imports: [RouterLink, StateComponent],
  template: `
    <section class="dashboard" aria-labelledby="dashboard-title" [attr.aria-busy]="state() === 'loading'">
      <header class="page-header">
        <div>
          <p class="eyebrow">{{ i18n.t('dashboard.eyebrow') }}</p>
          <h1 id="dashboard-title">{{ i18n.t('dashboard.title') }}</h1>
          <p class="page-subtitle">{{ i18n.t('dashboard.subtitle') }}</p>
        </div>
        <button type="button" class="secondary refresh" (click)="load()" [disabled]="state() === 'loading'">
          <img src="/assets/icons/refresh.svg" alt="" aria-hidden="true">
          {{ i18n.t('dashboard.refresh') }}
        </button>
      </header>

      <form class="filters dashboard-filters" aria-labelledby="dashboard-filters-title" (submit)="applyFilters($event)">
        <h2 id="dashboard-filters-title">{{ i18n.t('dashboard.filters') }}</h2>
        <label>{{ i18n.t('dashboard.organization') }}
          <select [value]="organizationId()" (change)="organizationId.set($any($event.target).value)">
            <option value="">{{ i18n.t('dashboard.allOrganizations') }}</option>
            @for (organization of data()?.organizations ?? []; track organization.id) {
              <option [value]="organization.id">{{ organization.name }} — {{ organization.code }}</option>
            }
          </select>
        </label>
        <label>{{ i18n.t('dashboard.dateFrom') }}<input type="date" [value]="dateFrom()" (input)="dateFrom.set($any($event.target).value)"></label>
        <label>{{ i18n.t('dashboard.dateTo') }}<input type="date" [value]="dateTo()" (input)="dateTo.set($any($event.target).value)"></label>
        <div class="filter-actions"><button type="submit">{{ i18n.t('dashboard.applyFilters') }}</button><button type="button" class="secondary" (click)="clearFilters()">{{ i18n.t('dashboard.clearFilters') }}</button></div>
        @if (filterError()) { <p class="error filter-error" role="alert">{{ filterError() }}</p> }
      </form>

      <section class="context" aria-labelledby="dashboard-context-title">
        <div>
          <h2 id="dashboard-context-title">{{ i18n.t('dashboard.context') }}</h2>
          <p>{{ scopeDescription() }}</p>
        </div>
        <dl>
          <div><dt>{{ i18n.t('dashboard.source') }}</dt><dd class="technical">{{ data()?.source ?? 'GET /indicators' }}</dd></div>
          <div><dt>{{ i18n.t('dashboard.updatedAt') }}</dt><dd>{{ data()?.generated_at ? i18n.formatDate(data()!.generated_at, { dateStyle: 'short', timeStyle: 'medium' }) : i18n.t('common.notAvailable') }}</dd></div>
          <div><dt>{{ i18n.t('dashboard.receivedAt') }}</dt><dd>{{ receivedAt() ? i18n.formatDate(receivedAt()!, { dateStyle: 'short', timeStyle: 'medium' }) : i18n.t('common.notAvailable') }}</dd></div>
        </dl>
        <p class="limitation"><strong>{{ i18n.t('dashboard.limitationTitle') }}</strong> {{ i18n.t('dashboard.limitation') }}</p>
      </section>

      @if (state() === 'loading') {
        <syn-state state="loading" [title]="i18n.t('dashboard.loadingTitle')" [message]="i18n.t('dashboard.loading')" />
      } @else if (state() === 'forbidden') {
        <syn-state state="forbidden" [title]="i18n.t('dashboard.forbiddenTitle')" [message]="i18n.t('dashboard.forbidden')" />
      } @else if (state() === 'unavailable') {
        <syn-state state="unavailable" [title]="i18n.t('dashboard.unavailableTitle')" [message]="i18n.t('dashboard.unavailable')"><button type="button" (click)="load()">{{ i18n.t('dashboard.tryAgain') }}</button></syn-state>
      } @else if (state() === 'error') {
        <syn-state state="error" [title]="i18n.t('dashboard.errorTitle')" [message]="i18n.t('dashboard.error')" />
      } @else {
        @if (state() === 'partial') {
          <syn-state state="partial" [title]="i18n.t('dashboard.partialTitle')" [message]="i18n.t('dashboard.partial')" />
        }
        @if (isEmpty()) {
          <syn-state state="success" [title]="i18n.t('dashboard.emptyTitle')" [message]="i18n.t('dashboard.empty')" />
        }
        <div class="indicator-grid" aria-label="Indicadores operacionais">
          <article class="indicator-card">
            <div class="indicator-heading"><img src="/assets/icons/processing.svg" alt="" aria-hidden="true"><h2>{{ i18n.t('dashboard.executions') }}</h2></div>
            <p class="indicator-value">{{ display(totalExecutions()) }}</p>
            <p class="indicator-detail">{{ i18n.t('dashboard.executionsDetail') }}</p>
            <a routerLink="/dashboard/related/executions" [queryParams]="navigationContext()">{{ i18n.t('dashboard.viewExecutions') }} <span aria-hidden="true">→</span></a>
          </article>
          <article class="indicator-card">
            <div class="indicator-heading"><img src="/assets/icons/production.svg" alt="" aria-hidden="true"><h2>{{ i18n.t('dashboard.workorders') }}</h2></div>
            <p class="indicator-value">{{ display(data()?.workorders?.total) }}</p>
            <p class="indicator-detail">{{ i18n.t('dashboard.partialReleases') }}: {{ display(data()?.workorders?.partially_released) }}</p>
            <a routerLink="/dashboard/related/workorders" [queryParams]="navigationContext()">{{ i18n.t('dashboard.viewWorkorders') }} <span aria-hidden="true">→</span></a>
          </article>
          <article class="indicator-card">
            <div class="indicator-heading"><img src="/assets/icons/queue.svg" alt="" aria-hidden="true"><h2>{{ i18n.t('dashboard.pending') }}</h2></div>
            <p class="indicator-value">{{ display(totalPending()) }}</p>
            <p class="indicator-detail">{{ i18n.t('dashboard.pendingDetail') }}</p>
            <a routerLink="/dashboard/related/pending-items" [queryParams]="navigationContext()">{{ i18n.t('dashboard.viewPending') }} <span aria-hidden="true">→</span></a>
          </article>
        </div>

        <section class="card quantities" aria-labelledby="quantities-title">
          <h2 id="quantities-title">{{ i18n.t('dashboard.quantities') }}</h2>
          <div class="quantity-list">
            @for (item of quantityItems; track item.key) {
              <div><span>{{ i18n.t(item.label) }}</span><strong>{{ display(data()?.quantities?.[item.key]) }}</strong></div>
            }
          </div>
          <p class="aggregate-note">{{ i18n.t('dashboard.auditNote') }}</p>
        </section>
      }
    </section>
  `,
  styles: [`
    .dashboard{display:grid;gap:var(--syn-space-5)}.page-header{border-bottom:1px solid var(--syn-border);margin:0;padding-bottom:var(--syn-space-4)}
    .refresh{gap:8px}.refresh img,.indicator-heading img{height:20px;width:20px}.dashboard-filters{align-items:end;display:grid;gap:12px;grid-template-columns:minmax(12rem,1.5fr) repeat(2,minmax(10rem,1fr)) auto}.dashboard-filters h2{font-size:16px;grid-column:1/-1;margin:0}.filter-actions{display:flex;gap:8px}.filter-error{grid-column:1/-1;margin:0}.context{align-items:start;background:var(--syn-bg-card);border:1px solid var(--syn-border);border-radius:var(--syn-radius);display:grid;gap:16px;grid-template-columns:minmax(15rem,1fr) auto;padding:16px 20px}.context h2{font-size:16px;margin-bottom:4px}.context p{color:var(--syn-text-secondary);margin:0}.context dl{display:flex;gap:24px;margin:0}.context dl div{display:grid;gap:3px}.context dt{color:var(--syn-text-secondary);font-size:12px}.context dd{font-size:13px;margin:0}.context .limitation{border-top:1px solid var(--syn-border);grid-column:1/-1;padding-top:12px}
    .indicator-grid{display:grid;gap:var(--syn-space-4);grid-template-columns:repeat(3,minmax(0,1fr))}.indicator-card{background:var(--syn-bg-card);border:1px solid var(--syn-border);border-radius:var(--syn-radius);box-shadow:var(--syn-shadow);display:flex;flex-direction:column;min-height:210px;padding:20px}.indicator-heading{align-items:center;display:flex;gap:10px}.indicator-heading img{background:var(--syn-primary-light);border-radius:var(--syn-radius-sm);box-sizing:content-box;padding:8px}.indicator-heading h2{font-size:16px;margin:0}.indicator-value{font-family:LGEIHeadline,sans-serif;font-size:clamp(32px,4vw,44px);font-weight:600;line-height:1;margin:24px 0 8px}.indicator-detail,.query-unavailable{color:var(--syn-text-secondary);font-size:13px}.indicator-card a{font-weight:600;margin-top:auto;text-decoration:none}.query-unavailable{margin-top:auto}.quantities{margin-top:4px}.quantity-list{display:grid;gap:0;grid-template-columns:repeat(4,1fr)}.quantity-list div{border-right:1px solid var(--syn-border);display:grid;gap:8px;padding:8px 20px}.quantity-list div:first-child{padding-left:0}.quantity-list div:last-child{border:0}.quantity-list span{color:var(--syn-text-secondary);font-size:13px}.quantity-list strong{font-family:JetBrainsMono,monospace;font-size:22px}.aggregate-note{border-top:1px solid var(--syn-border);color:var(--syn-text-secondary);font-size:13px;margin:18px 0 0;padding-top:14px}
    @media(max-width:1100px){.dashboard-filters{grid-template-columns:1fr 1fr}.filter-actions{align-self:end}.indicator-grid{grid-template-columns:1fr 1fr}.indicator-card:last-child{grid-column:1/-1}.context{grid-template-columns:1fr}.context .limitation{grid-column:auto}.context dl{border-top:1px solid var(--syn-border);padding-top:12px}.quantity-list{grid-template-columns:1fr 1fr}.quantity-list div{border-bottom:1px solid var(--syn-border)}.quantity-list div:nth-child(2){border-right:0}.quantity-list div:nth-child(3){padding-left:0}.quantity-list div:nth-child(n+3){border-bottom:0;padding-top:16px}}
    @media(max-width:600px){.dashboard-filters{grid-template-columns:1fr}.filter-actions{display:grid;grid-template-columns:1fr 1fr}.indicator-grid{grid-template-columns:1fr}.indicator-card:last-child{grid-column:auto}.context dl{display:grid;gap:12px}.page-header{align-items:stretch}.page-header button{width:100%}.quantity-list{grid-template-columns:1fr}.quantity-list div,.quantity-list div:nth-child(3){border-bottom:1px solid var(--syn-border);border-right:0;padding:14px 0}.quantity-list div:last-child{border-bottom:0}}
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
  readonly organizationId = signal(this.route.snapshot.queryParamMap.get('organization') ?? '');
  readonly dateFrom = signal(this.route.snapshot.queryParamMap.get('dateFrom') ?? '');
  readonly dateTo = signal(this.route.snapshot.queryParamMap.get('dateTo') ?? '');
  readonly filterError = signal('');
  private request?: Subscription;
  readonly navigationContext = computed(() => ({
    organization: this.organizationId() || null,
    dateFrom: this.dateFrom() || null,
    dateTo: this.dateTo() || null
  }));
  readonly quantityItems: Array<{ key: QuantityKey; label: 'dashboard.planned' | 'dashboard.produced' | 'dashboard.received' | 'dashboard.released' }> = [
    { key: 'planned', label: 'dashboard.planned' }, { key: 'produced', label: 'dashboard.produced' },
    { key: 'received', label: 'dashboard.received' }, { key: 'released', label: 'dashboard.released' }
  ];
  readonly totalExecutions = computed(() => this.sum(this.data()?.executions));
  readonly totalPending = computed(() => this.sum(this.data()?.pending_items));
  readonly isEmpty = computed(() => this.state() === 'ready' && [this.totalExecutions(), this.totalPending(), this.data()?.workorders?.total].every((value) => value === 0));
  readonly scopeDescription = computed(() => {
    const permission = this.session.profile()?.permissions.find((item) => item.key === 'dashboard.read');
    if (permission?.organizations === null) return this.i18n.t('dashboard.scopeGlobal');
    const count = permission?.organizations?.length ?? 0;
    return this.i18n.t('dashboard.scopeOrganizations', { count: this.i18n.formatNumber(count) });
  });

  ngOnInit(): void { this.load(); }
  ngOnDestroy(): void { this.request?.unsubscribe(); }
  applyFilters(event: Event): void {
    event.preventDefault();
    if (this.dateFrom() && this.dateTo() && this.dateFrom() > this.dateTo()) {
      this.filterError.set(this.i18n.t('dashboard.invalidPeriod'));
      return;
    }
    this.filterError.set('');
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: this.navigationContext(),
      replaceUrl: true
    }).then(() => this.load());
  }
  clearFilters(): void {
    this.organizationId.set(''); this.dateFrom.set(''); this.dateTo.set(''); this.filterError.set('');
    void this.router.navigate([], { relativeTo: this.route, queryParams: {}, replaceUrl: true }).then(() => this.load());
  }
  load(): void {
    this.request?.unsubscribe();
    this.state.set('loading');
    this.request = this.service.getIndicators({ organizationId: this.organizationId(), dateFrom: this.dateFrom(), dateTo: this.dateTo() }).subscribe({
      next: (data) => {
        this.data.set(data);
        this.receivedAt.set(new Date());
        this.state.set(this.isPartial(data) ? 'partial' : 'ready');
      },
      error: (failure: ApiFailure) => {
        this.data.set(null);
        this.receivedAt.set(null);
        this.state.set(failure.kind === 'forbidden' ? 'forbidden' : failure.kind === 'unavailable' ? 'unavailable' : 'error');
      }
    });
  }
  display(value: number | null | undefined): string { return value == null ? this.i18n.t('dashboard.absent') : this.i18n.formatNumber(value); }
  private sum(group: Record<string, number> | null | undefined): number | undefined { return group ? Object.values(group).reduce((total, value) => total + value, 0) : undefined; }
  private isPartial(data: Indicators): boolean {
    return data.workorders?.total == null || data.workorders?.partially_released == null || this.quantityItems.some((item) => data.quantities?.[item.key] == null);
  }
}
