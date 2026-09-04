import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { StateComponent } from '../../shared/ui/ui-kit';
import { PendingItem } from './query.models';
import { QueryService } from './query.service';

@Component({
  imports:[RouterLink,StateComponent],
  template:`<section class="pending-detail" aria-labelledby="pending-title"><button type="button" class="link-button" (click)="back()">← {{ i18n.t('queries.back') }}</button>@if(loading()){<syn-state state="loading" [title]="i18n.t('queries.loadingTitle')" [message]="i18n.t('queries.loadingDetail')" />}@if(failure()){<syn-state [state]="failure()?.kind==='not-found'?'empty':'error'" [title]="i18n.t('queries.errorTitle')" [message]="i18n.t('queries.error')" />}@if(item();as current){<header class="card"><p class="eyebrow">{{ i18n.t('queries.pending') }}</p><h1 id="pending-title">#{{ current.id }} · {{ current.category }}</h1><span class="badge">{{ current.status }}</span><dl><div><dt>Workorder</dt><dd><a [routerLink]="['/workorders',current.workorder_number]" [queryParams]="{from:returnUrl(),execution_id:current.execution_id}">{{ current.workorder_number }}</a></dd></div><div><dt>{{ i18n.t('queries.lot') }}</dt><dd>{{ current.lot_number||i18n.t('common.notAvailable') }}</dd></div><div><dt>Serial</dt><dd>{{ current.serial_number||i18n.t('common.notAvailable') }}</dd></div><div><dt>{{ i18n.t('queries.priority') }}</dt><dd>{{ current.priority }}</dd></div><div><dt>{{ i18n.t('queries.execution') }}</dt><dd><a [routerLink]="['/executions',current.execution_id]" [queryParams]="{from:returnUrl()}">{{ current.execution_id }}</a></dd></div><div><dt>{{ i18n.t('queries.updatedAt') }}</dt><dd>{{ i18n.formatDate(current.updated_at,{dateStyle:'medium',timeStyle:'short'}) }}</dd></div></dl><h2>{{ i18n.t('queries.reason') }}</h2><p>{{ current.reason||i18n.t('common.notAvailable') }}</p></header>}</section>`,
  styles:['.pending-detail{display:grid;gap:var(--syn-space-4);max-width:65rem}.pending-detail>button{width:max-content}header{border-left:4px solid var(--syn-primary)}dl{display:grid;gap:var(--syn-space-3);grid-template-columns:repeat(auto-fit,minmax(10rem,1fr))}dt{color:var(--syn-text-secondary)}dd{margin:0}']
})
export class RelatedPendingDetailComponent implements OnInit{
  readonly i18n=inject(I18nService);private route=inject(ActivatedRoute);private router=inject(Router);private api=inject(QueryService);readonly item=signal<PendingItem|null>(null);readonly loading=signal(true);readonly failure=signal<ApiFailure|null>(null);
  ngOnInit():void{const id=Number(this.route.snapshot.paramMap.get('pendingId'));this.api.pending(id).subscribe({next:value=>{this.item.set(value);this.loading.set(false)},error:(failure:ApiFailure)=>{this.failure.set(failure);this.loading.set(false)}})}
  back():void{void this.router.navigateByUrl(this.returnUrl())}returnUrl():string{const from=this.route.snapshot.queryParamMap.get('from');return from?.startsWith('/search?')||from==='/search'?from:'/search'}
}
