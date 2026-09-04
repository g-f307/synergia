import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { StateComponent, UiState } from '../../shared/ui/ui-kit';
import { ConsolidatedWorkorder, Workorder } from './query.models';
import { QueryService } from './query.service';

@Component({
  imports: [RouterLink, StateComponent],
  template: `
    <section class="workorder-detail" aria-labelledby="workorder-title">
      <button type="button" class="link-button back-link" (click)="back()">← {{ i18n.t('queries.back') }}</button>
      @if (loading()) { <syn-state state="loading" [title]="i18n.t('queries.loadingTitle')" [message]="i18n.t('queries.loadingDetail')" /> }
      @if (failureState(); as state) { <syn-state [state]="state" [title]="failureTitle()" [message]="failureMessage()" /> }
      @if (result(); as current) {
        <header class="card entity-header"><div><p class="eyebrow">Workorder</p><h1 id="workorder-title" class="technical">{{ current.workorder.workorder_number }}</h1><span class="badge">{{ current.workorder.processing_status }}</span></div><dl><div><dt>{{ i18n.t('queries.organization') }}</dt><dd>{{ current.workorder.organization_code || i18n.t('common.notAvailable') }}</dd></div><div><dt>{{ i18n.t('queries.execution') }}</dt><dd><a [routerLink]="['/executions',current.workorder.execution_id]" [queryParams]="{from:returnUrl()}">{{ current.workorder.execution_id }}</a></dd></div><div><dt>{{ i18n.t('queries.updatedAt') }}</dt><dd><time [attr.datetime]="current.workorder.updated_at">{{ i18n.formatDate(current.workorder.updated_at,{dateStyle:'medium',timeStyle:'short'}) }}</time></dd></div></dl></header>
        <section class="card"><h2>{{ i18n.t('queries.quantities') }}</h2><div class="metrics">@for (quantity of quantities(current.workorder); track quantity.key) {<div><strong>{{ quantity.value === null ? i18n.t('common.notAvailable') : i18n.formatNumber(quantity.value) }}</strong><span>{{ i18n.t(quantity.label) }}</span></div>}</div>@if(current.workorder.partially_released===null){<p>{{ i18n.t('queries.partialUnknown') }}</p>}@else if(current.workorder.partially_released){<p class="partial">{{ i18n.t('queries.partialRelease') }}</p>}</section>
        <section class="card"><h2>{{ i18n.t('queries.relatedEntities') }}</h2><div class="columns"><div><h3>{{ i18n.t('queries.lots') }}</h3>@if(!current.workorder.lots.length){<p>{{ i18n.t('queries.none') }}</p>}@for(lot of current.workorder.lots;track lot){<a [routerLink]="['/lots',lot]" [queryParams]="{from: returnUrl(),execution_id:current.workorder.execution_id}">{{ lot }}</a>}</div><div><h3>{{ i18n.t('queries.serials') }}</h3>@if(!current.workorder.serials.length){<p>{{ i18n.t('queries.none') }}</p>}@for(serial of current.workorder.serials;track serial){<a [routerLink]="['/serials',serial]" [queryParams]="{from: returnUrl(),execution_id:current.workorder.execution_id}">{{ serial }}</a>}</div></div></section>
        <section class="card"><h2>{{ i18n.t('queries.classifications') }}</h2>@if(!current.classifications.length){<p>{{ i18n.t('queries.none') }}</p>}@for(item of current.classifications;track item.classification_id){<article><div><strong>{{ item.rule_id }}</strong><span class="badge">{{ item.state }}</span></div><p>{{ item.justification }}</p><small>{{ item.entity_type }} · {{ item.entity_id }} · {{ item.data_quality }}</small></article>}</section>
        <section class="card"><h2>{{ i18n.t('queries.pending') }}</h2>@if(!current.pending_items.length){<p>{{ i18n.t('queries.none') }}</p>}@for(item of current.pending_items;track item.id){<article><div><a [routerLink]="['/pending-items',item.id]" [queryParams]="{from: returnUrl()}"><strong>{{ item.category }}</strong></a><span class="badge">{{ item.status }}</span></div><p>{{ item.reason || i18n.t('common.notAvailable') }}</p><small>{{ item.priority }} · {{ i18n.formatDate(item.updated_at,{dateStyle:'short',timeStyle:'short'}) }}</small></article>}</section>
        <section class="card"><h2>{{ i18n.t('queries.provenance') }}</h2><p>{{ i18n.t('queries.provenanceHelp') }}</p>@if(!current.provenance.length){<p>{{ i18n.t('queries.none') }}</p>}<dl class="provenance">@for(item of current.provenance;track $index){<div><dt>{{ item.field_name }}</dt><dd><strong>{{ item.source }}</strong><span>{{ observed(item.observed_value) }}</span><time [attr.datetime]="item.created_at">{{ i18n.formatDate(item.created_at,{dateStyle:'short',timeStyle:'short'}) }}</time></dd></div>}</dl></section>
      }
    </section>
  `,
  styles: ['.workorder-detail{display:grid;gap:var(--syn-space-4);max-width:75rem}.back-link{width:max-content}.entity-header{border-left:4px solid var(--syn-primary)}.entity-header>div:first-child{align-items:center;display:flex;flex-wrap:wrap;gap:var(--syn-space-3)}.entity-header h1,.entity-header p{margin:0}dl,.metrics,.columns{display:grid;gap:var(--syn-space-3);grid-template-columns:repeat(auto-fit,minmax(10rem,1fr))}dt{color:var(--syn-text-secondary)}dd{margin:0}.metrics div{background:var(--syn-bg);display:grid;padding:var(--syn-space-4)}.metrics strong{color:var(--syn-primary);font-size:1.4rem}.columns>div{display:grid;gap:var(--syn-space-2);align-content:start}article{border-bottom:1px solid var(--syn-border);padding:var(--syn-space-3) 0}article>div{align-items:center;display:flex;gap:var(--syn-space-3);justify-content:space-between}.provenance{grid-template-columns:1fr}.provenance div{border-bottom:1px solid var(--syn-border);display:grid;gap:var(--syn-space-2);grid-template-columns:minmax(10rem,1fr) 3fr;padding:var(--syn-space-2)}.provenance dd{display:flex;flex-wrap:wrap;gap:var(--syn-space-3);justify-content:space-between}.partial{border-left:.25rem solid var(--color-partial);padding-left:var(--syn-space-3)}']
})
export class WorkorderDetailComponent implements OnInit {
  readonly i18n = inject(I18nService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(QueryService);
  readonly loading = signal(true);
  readonly result = signal<ConsolidatedWorkorder | null>(null);
  readonly failure = signal<ApiFailure | null>(null);
  readonly failureState = computed<UiState | null>(() => this.toState(this.failure()));

  ngOnInit(): void { const number = this.route.snapshot.paramMap.get('workorderNumber') ?? ''; const executionId = this.route.snapshot.queryParamMap.get('execution_id') ?? undefined; this.api.workorder(number, executionId).subscribe({ next: value => { this.result.set(value); this.loading.set(false); }, error: (failure: ApiFailure) => { this.failure.set(failure); this.loading.set(false); } }); }
  back(): void { void this.router.navigateByUrl(this.returnUrl()); }
  returnUrl(): string { const from = this.route.snapshot.queryParamMap.get('from'); return from?.startsWith('/search?') || from === '/search' ? from : '/search'; }
  quantities(item: Workorder) { return [
    { key:'planned', label:'queries.quantity.planned' as const, value:item.planned_quantity }, { key:'produced', label:'queries.quantity.produced' as const, value:item.produced_quantity }, { key:'received', label:'queries.quantity.received' as const, value:item.received_quantity }, { key:'released', label:'queries.quantity.released' as const, value:item.released_quantity }, { key:'pending', label:'queries.quantity.pending' as const, value:item.pending_quantity }, { key:'retained', label:'queries.quantity.retained' as const, value:item.retained_quantity }
  ]; }
  observed(value: unknown): string { if (value === null || value === undefined) return this.i18n.t('common.notAvailable'); return typeof value === 'string' ? value : JSON.stringify(value); }
  failureTitle(): string { return this.i18n.t(this.failure()?.kind === 'not-found' ? 'queries.notFoundTitle' : this.failure()?.kind === 'forbidden' ? 'queries.forbiddenTitle' : 'queries.errorTitle'); }
  failureMessage(): string { return this.i18n.t(this.failure()?.kind === 'not-found' ? 'queries.notFound' : this.failure()?.kind === 'forbidden' ? 'queries.forbidden' : 'queries.error'); }
  private toState(failure: ApiFailure | null): UiState | null { if (!failure || failure.kind === 'unauthorized') return null; if (failure.kind === 'not-found') return 'empty'; if (failure.kind === 'forbidden') return 'forbidden'; if (failure.kind === 'unavailable') return 'unavailable'; return 'error'; }
}
