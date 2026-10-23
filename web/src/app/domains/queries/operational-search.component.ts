import { Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { EMPTY, catchError, map, of, switchMap, tap } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { PaginationComponent, ResponsiveTableComponent, StateComponent, UiState } from '../../shared/ui/ui-kit';
import { OperationalEntityType, OperationalSearchItem, OperationalSearchPage, OperationalSort } from './query.models';
import { QueryService } from './query.service';
import { isSearchPartial, isStale } from './query-response-state';

interface RecentSearch {
  type: OperationalEntityType;
  query: string;
  searchedAt: string;
}

@Component({
  imports: [RouterLink, PaginationComponent, ResponsiveTableComponent, StateComponent],
  template: `
    <section class="operational-search" aria-labelledby="query-title">
      <h1 id="query-title" class="sr-only">{{ i18n.t('queries.title') }}</h1>
      <form class="search-filters" (submit)="submit($event)">
        <div class="filter-field"><label for="query-type">{{ i18n.t('queries.type') }}</label><select id="query-type" name="type" [value]="type()" (change)="type.set($any($event.target).value)"><option value="workorder">Workorder</option><option value="lot">{{ i18n.t('queries.lot') }}</option><option value="serial">Serial</option></select></div>
        <div class="filter-field query-field"><label for="query-text">{{ i18n.t('queries.identifier') }}</label><input id="query-text" name="query" type="search" autocomplete="off" [value]="query()" (input)="query.set($any($event.target).value)" [placeholder]="i18n.t('queries.identifierPlaceholder')"></div>
        <div class="filter-field"><label for="query-sort">{{ i18n.t('queries.sort') }}</label><select id="query-sort" name="sort" [value]="sort()" (change)="sort.set($any($event.target).value)"><option value="updated_desc">{{ i18n.t('queries.sortUpdated') }}</option><option value="identifier_asc">{{ i18n.t('queries.sortIdentifier') }}</option></select></div>
        <div class="filter-field page-size-field"><label for="query-page-size">{{ i18n.t('queries.pageSize') }}</label><select id="query-page-size" name="pageSize" [value]="pageSize()" (change)="pageSize.set(+$any($event.target).value)"><option value="10">10</option><option value="25">25</option><option value="50">50</option></select></div>
        <button [disabled]="!query().length || loading()">{{ i18n.t('queries.search') }}</button>
      </form>

      @if (recentSearches().length) {
        <section class="recent-searches" aria-labelledby="recent-searches-title">
          <div><h2 id="recent-searches-title">{{ i18n.t('queries.recentTitle') }}</h2><p>{{ i18n.t('queries.recentHelp') }}</p></div>
          <div class="recent-list">
            @for (recent of recentSearches(); track recent.type + ':' + recent.query) {
              <button type="button" class="recent-search" (click)="repeatSearch(recent)"><span>{{ typeLabel(recent.type) }}</span><strong class="technical">{{ recent.query }}</strong><time [attr.datetime]="recent.searchedAt">{{ i18n.formatDate(recent.searchedAt,{dateStyle:'short',timeStyle:'short'}) }}</time></button>
            }
          </div>
        </section>
      }

      @if (loading()) { <syn-state state="loading" [title]="i18n.t('queries.loadingTitle')" [message]="i18n.t('queries.loading')" /> }
      @if (failureState(); as state) { <syn-state [state]="state" [title]="failureTitle()" [message]="failureMessage()" /> }
      @if (result(); as current) {
        @if (isPartial(current)) { <syn-state state="partial" [title]="i18n.t('queries.partialTitle')" [message]="i18n.t('queries.partial')" /> }
        @if (isOutdated(current)) { <syn-state state="stale" [title]="i18n.t('queries.staleTitle')" [message]="i18n.t('queries.stale')" /> }
        <section class="results" aria-live="polite">
          <header><div><h2>{{ i18n.t('queries.results') }}</h2><p>{{ i18n.t('queries.total', { count: i18n.formatNumber(current.pagination.total) }) }}</p></div><div class="reference"><span>{{ i18n.t('queries.source') }}: <strong>{{ current.source }}</strong></span><span>{{ i18n.t('queries.referenceTime') }}: <time [attr.datetime]="current.generated_at">{{ i18n.formatDate(current.generated_at,{dateStyle:'medium',timeStyle:'short'}) }}</time></span></div></header>
          @if (!current.items.length) { <syn-state state="empty" [title]="i18n.t('queries.emptyTitle')" [message]="current.pagination.total ? i18n.t('queries.emptyPage') : i18n.t('queries.empty')" /> }
          @else {
            <syn-responsive-table><table><thead><tr><th>{{ i18n.t('queries.identifier') }}</th><th>Workorder</th><th>{{ i18n.t('queries.status') }}</th><th>{{ i18n.t('queries.organization') }}</th><th>{{ i18n.t('queries.execution') }}</th><th>{{ i18n.t('queries.updatedAt') }}</th></tr></thead><tbody>@for (item of current.items; track resultKey(item)) {<tr><td><a [routerLink]="detailRoute(item)" [queryParams]="detailParams(item)"><strong class="technical">{{ item.identifier }}</strong></a></td><td class="technical">{{ item.workorder_number }}</td><td>{{ item.processing_status || i18n.t('common.notAvailable') }}</td><td>{{ item.organization_code || i18n.t('common.notAvailable') }}</td><td><a [routerLink]="['/executions',item.execution_id]" [queryParams]="{from: currentUrl()}">{{ item.execution_id }}</a></td><td><time [attr.datetime]="item.updated_at">{{ i18n.formatDate(item.updated_at,{dateStyle:'short',timeStyle:'short'}) }}</time></td></tr>}</tbody></table></syn-responsive-table>
          }
          @if(current.pagination.pages){<syn-pagination [page]="current.pagination.page" [pages]="current.pagination.pages" (pageChange)="changePage($event)" />}
        </section>
      }
    </section>
  `,
  styles: [`
    :host{display:block;height:100%;min-height:0}.operational-search{--line:color-mix(in srgb,var(--syn-text) 9%,transparent);background:var(--syn-bg-card);border:1px solid var(--line);border-radius:28px;display:grid;gap:18px;height:100%;min-height:0;overflow-x:hidden;overflow-y:auto;padding:clamp(20px,2.5vw,34px);scrollbar-gutter:stable}.sr-only{clip:rect(0,0,0,0);clip-path:inset(50%);height:1px;overflow:hidden;position:absolute;white-space:nowrap;width:1px}.search-filters{align-items:end;background:var(--syn-bg);border:1px solid var(--line);border-radius:16px;display:grid;gap:14px;grid-template-columns:minmax(9rem,.8fr) minmax(15rem,1.6fr) minmax(11rem,1fr) minmax(7rem,.55fr) auto;padding:18px}.filter-field{display:grid;gap:7px;min-width:0}.filter-field label{font-size:.76rem;font-weight:600}.filter-field input,.filter-field select{background:var(--syn-bg-card);color:var(--syn-text);min-height:44px;width:100%}.search-filters button{border-radius:999px;min-width:108px}.results{display:grid;gap:16px;min-width:0}.results>header{align-items:center;display:flex;gap:18px;justify-content:space-between}.results h2,.results p{margin:0}.results h2{font-size:1rem}.results header p{color:var(--syn-text-secondary);font-size:.78rem;margin-top:4px}.reference{color:var(--syn-text-secondary);display:flex;flex-wrap:wrap;font-size:.75rem;gap:8px 18px;justify-content:flex-end}.reference strong,.reference time{color:var(--syn-text);font-weight:600}.results syn-responsive-table{border:1px solid var(--line);border-radius:18px;display:block;overflow:hidden}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid var(--line);padding:14px 16px;text-align:left;white-space:nowrap}th{font-size:.7rem;letter-spacing:.02em;text-transform:none}tbody tr{transition:background var(--syn-transition)}tbody tr:hover{background:color-mix(in srgb,var(--syn-primary) 6%,var(--syn-bg-card))}tbody tr:last-child td{border-bottom:0}td a{color:var(--syn-text);font-weight:600;text-decoration:none}td a:hover,td a:focus-visible{color:var(--syn-primary);text-decoration:underline;text-underline-offset:3px}.results syn-pagination{justify-self:end}
    .operational-search{align-content:start}
    .recent-searches{align-items:start;border-bottom:1px solid var(--line);display:grid;gap:18px;grid-template-columns:minmax(150px,.35fr) 1fr;padding:2px 2px 18px}.recent-searches h2,.recent-searches p{margin:0}.recent-searches h2{font-size:1rem}.recent-searches p{color:var(--syn-text-secondary);font-size:.78rem;line-height:1.45;margin-top:4px}.recent-list{display:flex;gap:10px;justify-content:flex-end;min-width:0;overflow-x:auto;padding-bottom:3px}.recent-search{align-items:start;background:var(--syn-bg-card);border:1px solid var(--line);border-radius:14px;color:var(--syn-text);display:grid;flex:0 0 min(210px,75vw);gap:3px;padding:11px 13px;text-align:left}.recent-search:hover,.recent-search:focus-visible{background:color-mix(in srgb,var(--syn-primary) 6%,var(--syn-bg-card));border-color:color-mix(in srgb,var(--syn-primary) 30%,var(--line));color:var(--syn-text)}.recent-search span,.recent-search time{color:var(--syn-text-secondary);font-size:.68rem}.recent-search strong{font-size:.83rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    @media(max-width:1050px){.search-filters{grid-template-columns:1fr 1.5fr 1fr}.page-size-field{grid-column:1}.search-filters button{grid-column:3}}
    @media(max-width:720px){.operational-search{border-radius:20px;padding:18px}.search-filters{grid-template-columns:1fr 1fr}.query-field{grid-column:1/-1;grid-row:1}.page-size-field{grid-column:auto}.search-filters button{grid-column:1/-1;width:100%}.recent-searches{grid-template-columns:1fr}.recent-list{justify-content:flex-start}.results>header{align-items:start;display:grid}.reference{justify-content:flex-start}}
    @media(max-width:480px){.search-filters{grid-template-columns:1fr}.query-field{grid-column:auto;grid-row:auto}.search-filters button{grid-column:auto}.reference{display:grid}}
  `]
})
export class OperationalSearchComponent {
  private readonly recentStorageKey = 'synergia.operational-search.recent';
  readonly i18n = inject(I18nService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(QueryService);
  readonly type = signal<OperationalEntityType>('workorder');
  readonly query = signal('');
  readonly sort = signal<OperationalSort>('updated_desc');
  readonly pageSize = signal(25);
  readonly loading = signal(false);
  readonly result = signal<OperationalSearchPage | null>(null);
  readonly failure = signal<ApiFailure | null>(null);
  readonly recentSearches = signal<RecentSearch[]>(this.loadRecentSearches());
  readonly failureState = computed<UiState | null>(() => {
    const failure = this.failure();
    if (!failure || failure.kind === 'unauthorized') return null;
    if (failure.kind === 'forbidden') return 'forbidden';
    if (failure.kind === 'unavailable') return 'unavailable';
    return 'error';
  });

  constructor() {
    this.route.queryParamMap.pipe(
      tap((params) => {
        const type = params.get('type');
        const sort = params.get('sort');
        this.type.set(type === 'lot' || type === 'serial' ? type : 'workorder');
        this.query.set(params.get('query') ?? '');
        this.sort.set(sort === 'identifier_asc' ? sort : 'updated_desc');
        this.pageSize.set(this.positiveInt(params.get('pageSize'), 25, [10, 25, 50]));
        this.loading.set(this.query().length > 0);
        this.result.set(null);
        this.failure.set(null);
      }),
      switchMap((params) => {
        if (!this.query().length) return EMPTY;
        const page = this.positiveInt(params.get('page'), 1);
        return this.api.search(this.type(), this.query(), page, this.pageSize(), this.sort()).pipe(
          map((value) => ({ value, failure: null })),
          catchError((failure: ApiFailure) => of({ value: null, failure }))
        );
      }),
      takeUntilDestroyed()
    ).subscribe(({ value, failure }) => {
      this.result.set(value);
      this.failure.set(failure);
      this.loading.set(false);
      if (value) this.rememberSearch(value.entity_type, value.query);
    });
  }

  submit(event: Event): void { event.preventDefault(); if (!this.query().length) return; this.navigate(1); }
  repeatSearch(recent: RecentSearch): void { this.type.set(recent.type); this.query.set(recent.query); this.navigate(1); }
  typeLabel(type: OperationalEntityType): string { return type === 'lot' ? this.i18n.t('queries.lot') : type === 'serial' ? 'Serial' : 'Workorder'; }
  changePage(page: number): void { this.navigate(page); }
  detailRoute(item: OperationalSearchItem): (string | number)[] { return [`/${item.entity_type === 'workorder' ? 'workorders' : item.entity_type === 'lot' ? 'lots' : 'serials'}`, item.identifier]; }
  detailParams(item: OperationalSearchItem): Record<string, string> { return { from: this.currentUrl(), execution_id: item.execution_id }; }
  resultKey(item: OperationalSearchItem): string { return `${item.entity_type}:${item.execution_id}:${item.identifier}`; }
  isPartial(page: OperationalSearchPage): boolean { return isSearchPartial(page); }
  isOutdated(page: OperationalSearchPage): boolean { return isStale(page.generated_at); }
  currentUrl(): string { return this.router.url; }
  failureTitle(): string { return this.i18n.t(this.failure()?.kind === 'forbidden' ? 'queries.forbiddenTitle' : this.failure()?.kind === 'unavailable' ? 'queries.unavailableTitle' : 'queries.errorTitle'); }
  failureMessage(): string { return this.i18n.t(this.failure()?.kind === 'forbidden' ? 'queries.forbidden' : this.failure()?.kind === 'unavailable' ? 'queries.unavailable' : 'queries.error'); }

  private navigate(page: number): void { void this.router.navigate([], { relativeTo: this.route, queryParams: { type: this.type(), query: this.query(), page, pageSize: this.pageSize(), sort: this.sort() } }); }
  private positiveInt(value: string | null, fallback: number, allowed?: number[]): number { const parsed = Number(value); return Number.isInteger(parsed) && parsed > 0 && (!allowed || allowed.includes(parsed)) ? parsed : fallback; }
  private loadRecentSearches(): RecentSearch[] {
    try {
      const stored = JSON.parse(localStorage.getItem(this.recentStorageKey) ?? '[]');
      if (!Array.isArray(stored)) return [];
      return stored.filter((item): item is RecentSearch => item && ['workorder','lot','serial'].includes(item.type) && typeof item.query === 'string' && typeof item.searchedAt === 'string').slice(0, 5);
    } catch { return []; }
  }
  private rememberSearch(type: OperationalEntityType, query: string): void {
    const normalized = query.trim();
    if (!normalized) return;
    const recent = [{ type, query: normalized, searchedAt: new Date().toISOString() }, ...this.recentSearches().filter((item) => item.type !== type || item.query !== normalized)].slice(0, 5);
    this.recentSearches.set(recent);
    try { localStorage.setItem(this.recentStorageKey, JSON.stringify(recent)); } catch { /* Search remains available when browser storage is blocked. */ }
  }
}
