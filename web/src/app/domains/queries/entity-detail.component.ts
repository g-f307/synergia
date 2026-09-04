import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Observable } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { StateComponent, UiState } from '../../shared/ui/ui-kit';
import { Lot, Serial } from './query.models';
import { QueryService } from './query.service';
import { isEntityPartial, isStale } from './query-response-state';

@Component({
  imports: [RouterLink, StateComponent],
  template: `
    <section class="entity-detail" aria-labelledby="entity-title">
      <button type="button" class="link-button back-link" (click)="back()">← {{ i18n.t('queries.back') }}</button>
      @if(loading()){<syn-state state="loading" [title]="i18n.t('queries.loadingTitle')" [message]="i18n.t('queries.loadingDetail')" />}
      @if(failureState();as state){<syn-state [state]="state" [title]="failureTitle()" [message]="failureMessage()" />}
      @if(item();as current){
      @if(isPartial(current)){<syn-state state="partial" [title]="i18n.t('queries.partialTitle')" [message]="i18n.t('queries.partialDetail')" />}
      @if(isOutdated(current)){<syn-state state="stale" [title]="i18n.t('queries.staleTitle')" [message]="i18n.t('queries.stale')" />}
      <header class="card"><p class="eyebrow">{{ entityType()==='lot' ? i18n.t('queries.lot') : 'Serial' }}</p><h1 id="entity-title" class="technical">{{ identifier(current) }}</h1><dl><div><dt>Workorder</dt><dd><a [routerLink]="['/workorders',current.workorder_number]" [queryParams]="{from:returnUrl(),execution_id:current.execution_id}">{{ current.workorder_number }}</a></dd></div>@if(entityType()==='serial'){<div><dt>{{ i18n.t('queries.lot') }}</dt><dd>{{ serial(current).lot_number || i18n.t('common.notAvailable') }}</dd></div><div><dt>{{ i18n.t('queries.container') }}</dt><dd>{{ serial(current).container_number || i18n.t('common.notAvailable') }}</dd></div>}<div><dt>{{ i18n.t('queries.execution') }}</dt><dd><a [routerLink]="['/executions',current.execution_id]" [queryParams]="{from:returnUrl()}">{{ current.execution_id }}</a></dd></div><div><dt>{{ i18n.t('queries.updatedAt') }}</dt><dd><time [attr.datetime]="current.updated_at">{{ i18n.formatDate(current.updated_at,{dateStyle:'medium',timeStyle:'short'}) }}</time></dd></div></dl></header>
      @if(entityType()==='lot'){<section class="card"><h2>{{ i18n.t('queries.serials') }}</h2>@if(!lot(current).serials.length){<p>{{ i18n.t('queries.none') }}</p>}@for(number of lot(current).serials;track number){<a class="related" [routerLink]="['/serials',number]" [queryParams]="{from:returnUrl(),execution_id:current.execution_id}">{{ number }}</a>}</section>}}
    </section>
  `,
  styles: ['.entity-detail{display:grid;gap:var(--syn-space-4);max-width:65rem}.back-link{width:max-content}header.card{border-left:4px solid var(--syn-primary)}h1,p{margin-top:0}dl{display:grid;gap:var(--syn-space-3);grid-template-columns:repeat(auto-fit,minmax(10rem,1fr))}dt{color:var(--syn-text-secondary)}dd{margin:0}.related{display:block;margin:var(--syn-space-2) 0}']
})
export class EntityDetailComponent implements OnInit {
  readonly i18n=inject(I18nService); private route=inject(ActivatedRoute); private router=inject(Router); private api=inject(QueryService);
  readonly entityType=signal<'lot'|'serial'>('lot'); readonly item=signal<Lot|Serial|null>(null); readonly loading=signal(true); readonly failure=signal<ApiFailure|null>(null);
  readonly failureState=computed<UiState|null>(()=>{const value=this.failure();if(!value||value.kind==='unauthorized')return null;if(value.kind==='not-found')return 'empty';if(value.kind==='forbidden')return 'forbidden';if(value.kind==='unavailable')return 'unavailable';return 'error'});
  ngOnInit():void{const type=this.route.snapshot.data['entityType']==='serial'?'serial':'lot';this.entityType.set(type);const number=this.route.snapshot.paramMap.get(type==='lot'?'lotNumber':'serialNumber')??'';const executionId=this.route.snapshot.queryParamMap.get('execution_id')??undefined;const request:Observable<Lot|Serial>=type==='lot'?this.api.lot(number,executionId):this.api.serial(number,executionId);request.subscribe({next:value=>{this.item.set(value);this.loading.set(false)},error:(failure:ApiFailure)=>{this.failure.set(failure);this.loading.set(false)}})}
  back():void{void this.router.navigateByUrl(this.returnUrl())} returnUrl():string{const from=this.route.snapshot.queryParamMap.get('from');return from?.startsWith('/search?')||from==='/search'?from:'/search'}
  identifier(item:Lot|Serial):string{return this.entityType()==='lot'?this.lot(item).lot_number:this.serial(item).serial_number} lot(item:Lot|Serial):Lot{return item as Lot} serial(item:Lot|Serial):Serial{return item as Serial}
  isPartial(item:Lot|Serial):boolean{return isEntityPartial(item)} isOutdated(item:Lot|Serial):boolean{return isStale(item.updated_at)}
  failureTitle():string{return this.i18n.t(this.failure()?.kind==='not-found'?'queries.notFoundTitle':this.failure()?.kind==='forbidden'?'queries.forbiddenTitle':'queries.errorTitle')} failureMessage():string{return this.i18n.t(this.failure()?.kind==='not-found'?'queries.notFound':this.failure()?.kind==='forbidden'?'queries.forbidden':'queries.error')}
}
