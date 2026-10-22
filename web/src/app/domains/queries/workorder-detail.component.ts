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
      <header class="detail-toolbar">
        <button type="button" class="back-link" (click)="back()"><span aria-hidden="true">←</span>{{ i18n.t('queries.backWorkorders') }}</button>
        <h1 id="workorder-title">{{ i18n.t('queries.workorderDetailTitle') }}</h1>
      </header>

      <div class="detail-scroll">
        @if (loading()) {
          <syn-state state="loading" [title]="i18n.t('queries.loadingTitle')" [message]="i18n.t('queries.loadingDetail')" />
        }
        @if (failureState(); as state) {
          <syn-state [state]="state" [title]="failureTitle()" [message]="failureMessage()" />
        }
        @if (result(); as current) {
          <section class="overview" [attr.aria-label]="i18n.t('queries.status')">
            <div class="status-summary">
              <div><small>{{ i18n.t('queries.status') }}</small><strong class="status-pill" [attr.data-state]="statusKind(current.workorder.processing_status)">{{ statusLabel(current.workorder.processing_status) }}</strong></div>
            </div>
            <dl class="metadata">
              <div><dt>{{ i18n.t('queries.organization') }}</dt><dd>{{ current.workorder.organization_code || i18n.t('common.notAvailable') }}</dd></div>
              <div><dt>{{ i18n.t('queries.execution') }}</dt><dd><a class="technical" [routerLink]="['/executions',current.workorder.execution_id]" [queryParams]="{from:returnUrl()}">{{ current.workorder.execution_id }}</a></dd></div>
              <div><dt>{{ i18n.t('queries.updatedAt') }}</dt><dd><time [attr.datetime]="current.workorder.updated_at">{{ i18n.formatDate(current.workorder.updated_at,{dateStyle:'medium',timeStyle:'short'}) }}</time></dd></div>
            </dl>
          </section>

          <section class="detail-section quantities-section">
            <header><h2>{{ i18n.t('queries.quantities') }}</h2></header>
            <div class="metrics">
              @for (quantity of quantities(current.workorder); track quantity.key) {
                <div><span>{{ i18n.t(quantity.label) }}</span><strong>{{ quantity.value === null ? i18n.t('common.notAvailable') : i18n.formatNumber(quantity.value) }}</strong></div>
              }
            </div>
            @if(current.workorder.partially_released===null){<p class="inline-note">{{ i18n.t('queries.partialUnknown') }}</p>}
            @else if(current.workorder.partially_released){<p class="inline-note partial">{{ i18n.t('queries.partialRelease') }}</p>}
          </section>

          <section class="detail-section related-section">
            <header><h2>{{ i18n.t('queries.relatedEntities') }}</h2></header>
            <div class="related-columns">
              <div>
                <h3>{{ i18n.t('queries.lots') }} <span>{{ current.workorder.lots.length }}</span></h3>
                @if(!current.workorder.lots.length){<p class="empty-copy">{{ i18n.t('queries.none') }}</p>}
                <div class="link-list">@for(lot of current.workorder.lots;track lot){<a class="entity-link technical" [routerLink]="['/lots',lot]" [queryParams]="{from:currentUrl(),execution_id:current.workorder.execution_id}">{{ lot }}<span aria-hidden="true">›</span></a>}</div>
              </div>
              <div>
                <h3>{{ i18n.t('queries.serials') }} <span>{{ current.workorder.serials.length }}</span></h3>
                @if(!current.workorder.serials.length){<p class="empty-copy">{{ i18n.t('queries.none') }}</p>}
                <div class="link-list">@for(serial of current.workorder.serials;track serial){<a class="entity-link technical" [routerLink]="['/serials',serial]" [queryParams]="{from:returnUrl(),execution_id:current.workorder.execution_id}">{{ serial }}<span aria-hidden="true">›</span></a>}</div>
              </div>
            </div>
          </section>

          <section class="detail-section">
            <header><h2>{{ i18n.t('queries.classifications') }}</h2><span class="count">{{ current.classifications.length }}</span></header>
            @if(!current.classifications.length){<p class="empty-copy">{{ i18n.t('queries.none') }}</p>}
            <div class="record-list">@for(item of current.classifications;track item.classification_id){<article><div><strong>{{ item.rule_id }}</strong><span class="record-state">{{ item.state }}</span></div><p>{{ item.justification }}</p><small>{{ item.data_quality }}</small></article>}</div>
          </section>

          <section class="detail-section">
            <header><h2>{{ i18n.t('queries.pending') }}</h2><span class="count">{{ current.pending_items.length }}</span></header>
            @if(!current.pending_items.length){<p class="empty-copy">{{ i18n.t('queries.none') }}</p>}
            <div class="record-list">@for(item of current.pending_items;track item.id){<article><div><strong>{{ item.category }}</strong><span class="record-state">{{ item.status }}</span></div><p>{{ item.reason || i18n.t('common.notAvailable') }}</p><small>{{ item.priority }} · {{ i18n.formatDate(item.updated_at,{dateStyle:'short',timeStyle:'short'}) }}</small></article>}</div>
          </section>

          <section class="detail-section provenance-section">
            <header><div><h2>{{ i18n.t('queries.provenance') }}</h2><p>{{ i18n.t('queries.provenanceHelp') }}</p></div><span class="count">{{ current.provenance.length }}</span></header>
            @if(!current.provenance.length){<p class="empty-copy">{{ i18n.t('queries.none') }}</p>}
            <dl class="provenance">@for(item of current.provenance;track $index){<div><dt>{{ item.field_name }}</dt><dd><strong>{{ item.source }}</strong><span>{{ observed(item.observed_value) }}</span><time [attr.datetime]="item.created_at">{{ i18n.formatDate(item.created_at,{dateStyle:'short',timeStyle:'short'}) }}</time></dd></div>}</dl>
          </section>
        }
      </div>
    </section>
  `,
  styleUrl: './workorder-detail.component.css'
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
  readonly workorderNumber = this.route.snapshot.paramMap.get('workorderNumber') ?? '';

  ngOnInit(): void {
    const executionId = this.route.snapshot.queryParamMap.get('execution_id') ?? undefined;
    this.api.workorder(this.workorderNumber, executionId).subscribe({
      next: value => { this.result.set(value); this.loading.set(false); },
      error: (failure: ApiFailure) => { this.failure.set(failure); this.loading.set(false); }
    });
  }
  back(): void { void this.router.navigateByUrl(this.returnUrl()); }
  currentUrl(): string { return this.router.url; }
  returnUrl(): string {
    const from = this.route.snapshot.queryParamMap.get('from');
    const allowed = ['/search', '/dashboard/related/workorders'];
    return from && allowed.some(path => from === path || from.startsWith(`${path}?`)) ? from : '/search';
  }
  quantities(item: Workorder) { return [
    { key:'planned', label:'queries.quantity.planned' as const, value:item.planned_quantity },
    { key:'produced', label:'queries.quantity.produced' as const, value:item.produced_quantity },
    { key:'received', label:'queries.quantity.received' as const, value:item.received_quantity },
    { key:'released', label:'queries.quantity.released' as const, value:item.released_quantity },
    { key:'pending', label:'queries.quantity.pending' as const, value:item.pending_quantity },
    { key:'retained', label:'queries.quantity.retained' as const, value:item.retained_quantity }
  ]; }
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
  observed(value: unknown): string {
    if (value === null || value === undefined) return this.i18n.t('common.notAvailable');
    return typeof value === 'string' ? value : JSON.stringify(value);
  }
  failureTitle(): string { return this.i18n.t(this.failure()?.kind === 'not-found' ? 'queries.notFoundTitle' : this.failure()?.kind === 'forbidden' ? 'queries.forbiddenTitle' : 'queries.errorTitle'); }
  failureMessage(): string { return this.i18n.t(this.failure()?.kind === 'not-found' ? 'queries.notFound' : this.failure()?.kind === 'forbidden' ? 'queries.forbidden' : 'queries.error'); }
  private toState(failure: ApiFailure | null): UiState | null {
    if (!failure || failure.kind === 'unauthorized') return null;
    if (failure.kind === 'not-found') return 'empty';
    if (failure.kind === 'forbidden') return 'forbidden';
    if (failure.kind === 'unavailable') return 'unavailable';
    return 'error';
  }
}
