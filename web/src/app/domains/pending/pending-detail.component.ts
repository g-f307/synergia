import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { StateComponent, UiState } from '../../shared/ui/ui-kit';
import { PendingItem } from './pending.models';
import { PENDING_PRIORITY_KEYS, PENDING_STATUS_KEYS } from './pending-labels';
import { PendingService } from './pending.service';
import { pendingIsPartial, pendingIsStale, pendingKind } from './pending-state';

@Component({
  imports: [RouterLink, StateComponent],
  template: `
    <section class="pending-detail" aria-labelledby="pending-detail-title">
      <button type="button" class="link-button" (click)="back()">← {{ i18n.t('pending.back') }}</button>
      @if(loading()){<syn-state state="loading" [title]="i18n.t('pending.loadingTitle')" [message]="i18n.t('pending.loadingDetail')" />}
      @if(failureState();as state){<syn-state [state]="state" [title]="failureTitle()" [message]="failureMessage()" />}
      @if(item();as current){
        @if(isPartial(current)){<syn-state state="partial" [title]="i18n.t('pending.partialTitle')" [message]="i18n.t('pending.partialDetail')" />}
        @if(isStale(current)){<syn-state state="stale" [title]="i18n.t('queries.staleTitle')" [message]="i18n.t('queries.stale')" />}
        <header class="card"><div><p class="eyebrow">{{ i18n.t('pending.eyebrow') }}</p><h1 id="pending-detail-title">#{{ current.id }} · <span class="technical">{{ current.category }}</span></h1><span class="badge" [attr.data-pending-kind]="kind(current)">{{ kindLabel(current) }}</span></div><dl><div><dt>{{ i18n.t('pending.status') }}</dt><dd>{{ statusLabel(current.status) }}</dd></div><div><dt>{{ i18n.t('pending.priority') }}</dt><dd>{{ priorityLabel(current.priority) }} ({{ current.priority_score }})</dd></div><div><dt>{{ i18n.t('pending.area') }}</dt><dd>{{ current.responsible_area || i18n.t('common.notAvailable') }}</dd></div><div><dt>{{ i18n.t('queries.updatedAt') }}</dt><dd><time [attr.datetime]="current.updated_at">{{ i18n.formatDate(current.updated_at,{dateStyle:'medium',timeStyle:'short'}) }}</time></dd></div></dl></header>
        <section class="card"><h2>{{ i18n.t('pending.rule') }}</h2><dl><div><dt>{{ i18n.t('pending.ruleCode') }}</dt><dd class="technical">{{ current.rule_id || current.category }}</dd></div><div><dt>{{ i18n.t('pending.ruleVersion') }}</dt><dd class="technical">{{ current.rule_catalog_version || i18n.t('common.notAvailable') }}</dd></div><div><dt>{{ i18n.t('pending.reason') }}</dt><dd>{{ current.reason || i18n.t('pending.reasonMissing') }}</dd></div></dl></section>
        <section class="card"><h2>{{ i18n.t('pending.relationships') }}</h2><div class="relationships"><a [routerLink]="['/workorders',current.workorder_number]" [queryParams]="{from:returnUrl(),execution_id:current.execution_id}">Workorder <span class="technical">{{ current.workorder_number }}</span></a>@if(current.lot_number){<a [routerLink]="['/lots',current.lot_number]" [queryParams]="{from:returnUrl(),execution_id:current.execution_id}">{{ i18n.t('queries.lot') }} <span class="technical">{{ current.lot_number }}</span></a>}@if(current.serial_number){<a [routerLink]="['/serials',current.serial_number]" [queryParams]="{from:returnUrl(),execution_id:current.execution_id}">Serial <span class="technical">{{ current.serial_number }}</span></a>}<a [routerLink]="['/executions',current.execution_id]" [queryParams]="{from:returnUrl()}">{{ i18n.t('queries.execution') }} <span class="technical">{{ current.execution_id }}</span></a></div></section>
        <section class="card"><h2>{{ i18n.t('pending.evidence') }}</h2>@if(hasEvidence(current)){<pre>{{ evidence(current) }}</pre>}@else{<p>{{ i18n.t('pending.evidenceMissing') }}</p>}</section>
        <aside class="scope-note">{{ i18n.t('pending.readOnly') }}</aside>
      }
    </section>
  `,
  styles: ['.pending-detail{display:grid;gap:var(--syn-space-4);max-width:72rem}.pending-detail>button{width:max-content}header{align-items:start;border-left:4px solid var(--syn-primary);display:flex;gap:var(--syn-space-6);justify-content:space-between}header h1{margin-bottom:var(--syn-space-3)}dl{display:grid;gap:var(--syn-space-3);grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));margin:0;min-width:50%}dt{color:var(--syn-text-secondary);font-size:.875rem}dd{margin:0}.relationships{display:flex;flex-wrap:wrap;gap:var(--syn-space-4)}pre{background:var(--syn-bg);border:1px solid var(--syn-border);border-radius:var(--syn-radius-sm);overflow:auto;padding:var(--syn-space-4);white-space:pre-wrap}.scope-note{color:var(--syn-text-secondary);font-size:.875rem}.badge[data-pending-kind=post-release]{color:var(--syn-error)}.badge[data-pending-kind=technical]{color:var(--syn-attention)}.badge[data-pending-kind=partial]{color:var(--syn-partial)}@media(max-width:700px){header{display:grid}dl{min-width:0}}']
})
export class PendingDetailComponent implements OnInit {
  readonly i18n=inject(I18nService);private route=inject(ActivatedRoute);private router=inject(Router);private api=inject(PendingService);readonly item=signal<PendingItem|null>(null);readonly loading=signal(true);readonly failure=signal<ApiFailure|null>(null);
  readonly failureState=computed<UiState|null>(()=>{const kind=this.failure()?.kind;if(!kind||kind==='unauthorized')return null;if(kind==='not-found')return 'empty';if(kind==='forbidden')return 'forbidden';if(kind==='unavailable')return 'unavailable';return 'error'});
  ngOnInit():void{const id=Number(this.route.snapshot.paramMap.get('pendingId'));if(!Number.isSafeInteger(id)||id<=0){void this.router.navigateByUrl('/pending-items');return}this.api.detail(id).subscribe({next:value=>{this.item.set(value);this.loading.set(false)},error:(failure:ApiFailure)=>{this.failure.set(failure);this.loading.set(false)}})}
  back():void{void this.router.navigateByUrl(this.returnUrl())}returnUrl():string{const from=this.route.snapshot.queryParamMap.get('from');return from?.startsWith('/pending-items?')||from==='/pending-items'?from:'/pending-items'}
  kind(item:PendingItem){return pendingKind(item)}kindLabel(item:PendingItem):string{const kind=pendingKind(item);if(kind==='pre-release')return this.i18n.t('pending.kind.preRelease');if(kind==='post-release')return this.i18n.t('pending.kind.postRelease');if(kind==='technical')return this.i18n.t('pending.kind.technical');if(kind==='partial')return this.i18n.t('pending.kind.partial');return this.i18n.t('pending.kind.operational')}
  priorityLabel(priority:string):string{return this.i18n.t(PENDING_PRIORITY_KEYS[priority]??'pending.priority.normal')}statusLabel(status:string):string{return this.i18n.t(PENDING_STATUS_KEYS[status]??'pending.status.open')}
  isPartial(item:PendingItem):boolean{return pendingIsPartial(item)}isStale(item:PendingItem):boolean{return pendingIsStale(item.updated_at)}hasEvidence(item:PendingItem):boolean{return Object.keys(item.evidence).length>0}evidence(item:PendingItem):string{return JSON.stringify(item.evidence,null,2)}
  failureTitle():string{return this.i18n.t(this.failure()?.kind==='not-found'?'pending.notFoundTitle':this.failure()?.kind==='forbidden'?'pending.forbiddenTitle':this.failure()?.kind==='unavailable'?'pending.unavailableTitle':'pending.errorTitle')}
  failureMessage():string{return this.i18n.t(this.failure()?.kind==='not-found'?'pending.notFound':this.failure()?.kind==='forbidden'?'pending.forbidden':this.failure()?.kind==='unavailable'?'pending.unavailable':'pending.error')}
}
