import { Location } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Observable } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { StateComponent, UiState } from '../../shared/ui/ui-kit';
import { Lot, Serial } from './query.models';
import { QueryService } from './query.service';
import { isEntityPartial } from './query-response-state';

@Component({
  imports: [RouterLink, StateComponent],
  template: `
    <section class="entity-detail" aria-labelledby="entity-title">
      <header class="detail-toolbar" [class.serial-toolbar]="entityType()==='serial'">
        <button type="button" class="back-link" (click)="back()"><span aria-hidden="true">←</span>{{ i18n.t('queries.back') }}</button>
        <div class="toolbar-heading">
          <h1 id="entity-title">{{ entityType()==='lot' ? i18n.t('queries.lotDetailTitle') : i18n.t('queries.serialDetailTitle') }}</h1>
        </div>
      </header>

      <div class="detail-scroll">
        @if(loading()){<syn-state state="loading" [title]="i18n.t('queries.loadingTitle')" [message]="i18n.t('queries.loadingDetail')" />}
        @if(failureState();as state){<syn-state [state]="state" [title]="failureTitle()" [message]="failureMessage()" />}
        @if(item();as current){
          @if(entityType()==='serial'&&isPartial(current)){<syn-state state="partial" [title]="i18n.t('queries.partialTitle')" [message]="i18n.t('queries.partialDetail')" />}
          <section class="overview" [attr.aria-label]="entityType()==='lot' ? i18n.t('queries.lot') : 'Serial'">
            <header class="entity-summary">
              <span>{{ entityType()==='lot' ? i18n.t('queries.lot') : 'Serial' }}</span>
              <h2 class="technical" data-testid="entity-identifier">{{ identifier(current) }}</h2>
            </header>
            <dl class="metadata-strip">
              <div><dt>Workorder</dt><dd><a class="metadata-link technical" [routerLink]="['/workorders',current.workorder_number]" [queryParams]="{from:returnUrl(),execution_id:current.execution_id}">{{ current.workorder_number }}<span aria-hidden="true">›</span></a></dd></div>
              @if(entityType()==='serial'){
                <div><dt>{{ i18n.t('queries.lot') }}</dt><dd>
                  @if(serial(current).lot_number){
                    <a class="metadata-link technical" [routerLink]="['/lots',serial(current).lot_number]" [queryParams]="{from:currentDetailUrl(current),execution_id:current.execution_id}">{{ serial(current).lot_number }}<span aria-hidden="true">›</span></a>
                  } @else { {{ i18n.t('common.notAvailable') }} }
                </dd></div>
                <div><dt>{{ i18n.t('queries.container') }}</dt><dd>{{ serial(current).container_number || i18n.t('common.notAvailable') }}</dd></div>
              }
              <div><dt>{{ i18n.t('queries.execution') }}</dt><dd><a class="metadata-link technical" [routerLink]="['/executions',current.execution_id]" [queryParams]="{from:returnUrl()}">{{ current.execution_id }}<span aria-hidden="true">›</span></a></dd></div>
              <div><dt>{{ i18n.t('queries.updatedAt') }}</dt><dd><time [attr.datetime]="current.updated_at">{{ i18n.formatDate(current.updated_at,{dateStyle:'medium',timeStyle:'short'}) }}</time></dd></div>
            </dl>
          </section>

          @if(entityType()==='lot'){
            <section class="detail-section related-section related-records">
              <header><h2>{{ i18n.t('queries.relatedSerials') }}</h2><span class="count">{{ lot(current).serials.length }}</span></header>
              @if(!lot(current).serials.length){<p class="empty-copy">{{ i18n.t('queries.none') }}</p>}
              <div class="serial-list">@for(number of lot(current).serials;track number){<a class="related" [routerLink]="['/serials',number]" [queryParams]="{from:currentDetailUrl(current),execution_id:current.execution_id}"><span><small>Serial</small><strong class="technical">{{ number }}</strong></span><span class="row-chevron" aria-hidden="true">›</span></a>}</div>
            </section>
          }
        }
      </div>
    </section>
  `,
  styleUrl: './entity-detail.component.css'
})
export class EntityDetailComponent implements OnInit {
  readonly i18n=inject(I18nService); private route=inject(ActivatedRoute); private router=inject(Router); private location=inject(Location); private api=inject(QueryService);
  readonly entityType=signal<'lot'|'serial'>('lot'); readonly item=signal<Lot|Serial|null>(null); readonly loading=signal(true); readonly failure=signal<ApiFailure|null>(null);
  readonly failureState=computed<UiState|null>(()=>{const value=this.failure();if(!value||value.kind==='unauthorized')return null;if(value.kind==='not-found')return 'empty';if(value.kind==='forbidden')return 'forbidden';if(value.kind==='unavailable')return 'unavailable';return 'error'});
  ngOnInit():void{const type=this.route.snapshot.data['entityType']==='serial'?'serial':'lot';this.entityType.set(type);const number=this.route.snapshot.paramMap.get(type==='lot'?'lotNumber':'serialNumber')??'';const executionId=this.route.snapshot.queryParamMap.get('execution_id')??undefined;const request:Observable<Lot|Serial>=type==='lot'?this.api.lot(number,executionId):this.api.serial(number,executionId);request.subscribe({next:value=>{this.item.set(value);this.loading.set(false)},error:(failure:ApiFailure)=>{this.failure.set(failure);this.loading.set(false)}})}
  back():void{const from=this.explicitReturnUrl();if(from){void this.router.navigateByUrl(from);return}this.location.back()}
  returnUrl():string{return this.explicitReturnUrl()??'/search'}
  private explicitReturnUrl():string|null{const from=this.route.snapshot.queryParamMap.get('from');const allowed=['/search','/workorders/','/lots/'];return from&&allowed.some(path=>from===path||from.startsWith(path))?from:null}
  currentDetailUrl(item:Lot|Serial):string{const segment=this.entityType()==='lot'?'lots':'serials';return `/${segment}/${encodeURIComponent(this.identifier(item))}?execution_id=${encodeURIComponent(item.execution_id)}`}
  identifier(item:Lot|Serial):string{return this.entityType()==='lot'?this.lot(item).lot_number:this.serial(item).serial_number} lot(item:Lot|Serial):Lot{return item as Lot} serial(item:Lot|Serial):Serial{return item as Serial}
  isPartial(item:Lot|Serial):boolean{return isEntityPartial(item)}
  failureTitle():string{return this.i18n.t(this.failure()?.kind==='not-found'?'queries.notFoundTitle':this.failure()?.kind==='forbidden'?'queries.forbiddenTitle':'queries.errorTitle')} failureMessage():string{return this.i18n.t(this.failure()?.kind==='not-found'?'queries.notFound':this.failure()?.kind==='forbidden'?'queries.forbidden':'queries.error')}
}
