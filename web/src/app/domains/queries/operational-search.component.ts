import { Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { EMPTY, catchError, map, of, switchMap, tap } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { PaginationComponent, ResponsiveTableComponent, StateComponent, UiState } from '../../shared/ui/ui-kit';
import { OperationalEntityType, OperationalSearchItem, OperationalSearchPage, OperationalSort } from './query.models';
import { QueryService } from './query.service';

@Component({
  imports: [RouterLink, PaginationComponent, ResponsiveTableComponent, StateComponent],
  template: `
    <section class="operational-search" aria-labelledby="query-title">
      <header class="page-header"><div><p class="eyebrow">{{ i18n.t('queries.eyebrow') }}</p><h1 id="query-title">{{ i18n.t('queries.title') }}</h1><p class="page-subtitle">{{ i18n.t('queries.help') }}</p></div></header>
      <form class="card filters" (submit)="submit($event)">
        <label for="query-type">{{ i18n.t('queries.type') }}<select id="query-type" [value]="type()" (change)="type.set($any($event.target).value)"><option value="workorder">Workorder</option><option value="lot">{{ i18n.t('queries.lot') }}</option><option value="serial">Serial</option></select></label>
        <label for="query-text">{{ i18n.t('queries.identifier') }}<input id="query-text" type="search" autocomplete="off" [value]="query()" (input)="query.set($any($event.target).value)" [placeholder]="i18n.t('queries.identifierPlaceholder')"></label>
        <label for="query-sort">{{ i18n.t('queries.sort') }}<select id="query-sort" [value]="sort()" (change)="sort.set($any($event.target).value)"><option value="updated_desc">{{ i18n.t('queries.sortUpdated') }}</option><option value="identifier_asc">{{ i18n.t('queries.sortIdentifier') }}</option></select></label>
        <label for="query-page-size">{{ i18n.t('queries.pageSize') }}<select id="query-page-size" [value]="pageSize()" (change)="pageSize.set(+$any($event.target).value)"><option value="10">10</option><option value="25">25</option><option value="50">50</option></select></label>
        <button [disabled]="!query().length || loading()">{{ i18n.t('queries.search') }}</button>
      </form>

      @if (loading()) { <syn-state state="loading" [title]="i18n.t('queries.loadingTitle')" [message]="i18n.t('queries.loading')" /> }
      @if (failureState(); as state) { <syn-state [state]="state" [title]="failureTitle()" [message]="failureMessage()" /> }
      @if (result(); as current) {
        <section class="card results" aria-live="polite">
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
  styles: ['.operational-search{display:grid;gap:var(--syn-space-5);max-width:78rem}.page-header{border-bottom:1px solid var(--syn-border);padding-bottom:var(--syn-space-4)}.filters{align-items:end;display:grid;gap:var(--syn-space-4);grid-template-columns:repeat(4,minmax(8rem,1fr)) auto}.results{display:grid;gap:var(--syn-space-4)}.results>header{align-items:start;display:flex;gap:var(--syn-space-4);justify-content:space-between}.results h2,.results p{margin:0}.reference{display:grid;font-size:.875rem;gap:var(--syn-space-1);text-align:right}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid var(--syn-border);padding:var(--syn-space-3);text-align:left;white-space:nowrap}@media(max-width:900px){.filters{grid-template-columns:1fr 1fr}.filters button{grid-column:1/-1}.results>header{display:grid}.reference{text-align:left}}@media(max-width:560px){.filters{grid-template-columns:1fr}}']
})
export class OperationalSearchComponent {
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
    });
  }

  submit(event: Event): void { event.preventDefault(); if (!this.query().length) return; this.navigate(1); }
  changePage(page: number): void { this.navigate(page); }
  detailRoute(item: OperationalSearchItem): (string | number)[] { return [`/${item.entity_type === 'workorder' ? 'workorders' : item.entity_type === 'lot' ? 'lots' : 'serials'}`, item.identifier]; }
  detailParams(item: OperationalSearchItem): Record<string, string> { return { from: this.currentUrl(), execution_id: item.execution_id }; }
  resultKey(item: OperationalSearchItem): string { return `${item.entity_type}:${item.execution_id}:${item.identifier}`; }
  currentUrl(): string { return this.router.url; }
  failureTitle(): string { return this.i18n.t(this.failure()?.kind === 'forbidden' ? 'queries.forbiddenTitle' : this.failure()?.kind === 'unavailable' ? 'queries.unavailableTitle' : 'queries.errorTitle'); }
  failureMessage(): string { return this.i18n.t(this.failure()?.kind === 'forbidden' ? 'queries.forbidden' : this.failure()?.kind === 'unavailable' ? 'queries.unavailable' : 'queries.error'); }

  private navigate(page: number): void { void this.router.navigate([], { relativeTo: this.route, queryParams: { type: this.type(), query: this.query(), page, pageSize: this.pageSize(), sort: this.sort() } }); }
  private positiveInt(value: string | null, fallback: number, allowed?: number[]): number { const parsed = Number(value); return Number.isInteger(parsed) && parsed > 0 && (!allowed || allowed.includes(parsed)) ? parsed : fallback; }
}
