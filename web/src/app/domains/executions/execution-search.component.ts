import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { PaginationComponent, StateComponent } from '../../shared/ui/ui-kit';
import { ExecutionCatalogFilters, ExecutionCatalogItem, Page } from './execution.models';
import { ExecutionService } from './execution.service';

@Component({
  imports: [PaginationComponent, StateComponent],
  template: `
<section class="execution-catalog" aria-labelledby="execution-catalog-title">
 <header class="page-header"><div><p class="eyebrow">{{i18n.t('executions.eyebrow')}}</p><h1 id="execution-catalog-title">{{i18n.t('executions.catalogTitle')}}</h1><p class="page-subtitle">{{i18n.t('executions.catalogHelp')}}</p></div></header>
 <form class="card filters" (submit)="apply($event)">
  <label>{{i18n.t('executions.id')}}<input [value]="executionId()" (input)="executionId.set($any($event.target).value)" autocomplete="off"></label>
  <label>{{i18n.t('executions.organization')}}<input [value]="organizationId()" (input)="organizationId.set($any($event.target).value)" autocomplete="off"></label>
  <label>{{i18n.t('executions.persistedState')}}<input [value]="status()" (input)="status.set($any($event.target).value)"></label>
  <label>{{i18n.t('executions.publicState')}}<select [value]="lifecycle()" (change)="lifecycle.set($any($event.target).value)"><option value="">{{i18n.t('executions.all')}}</option><option value="active">{{i18n.t('executions.lifecycle.active')}}</option><option value="completed">{{i18n.t('executions.lifecycle.completed')}}</option><option value="partial">{{i18n.t('executions.lifecycle.partial')}}</option><option value="failed">{{i18n.t('executions.lifecycle.failed')}}</option></select></label>
  <label>{{i18n.t('executions.source')}}<input [value]="source()" (input)="source.set($any($event.target).value)"></label>
  <label>{{i18n.t('executions.fileType')}}<input [value]="fileType()" (input)="fileType.set($any($event.target).value)"></label>
  <label>{{i18n.t('executions.dateFrom')}}<input type="datetime-local" [value]="dateFrom()" (input)="dateFrom.set($any($event.target).value)"></label>
  <label>{{i18n.t('executions.dateTo')}}<input type="datetime-local" [value]="dateTo()" (input)="dateTo.set($any($event.target).value)"></label>
  <label>{{i18n.t('executions.sort')}}<select [value]="sort()" (change)="sort.set($any($event.target).value)"><option value="newest">{{i18n.t('executions.newest')}}</option><option value="oldest">{{i18n.t('executions.oldest')}}</option></select></label>
  <div class="actions"><button type="submit">{{i18n.t('executions.filter')}}</button><button type="button" class="secondary" (click)="clear()">{{i18n.t('executions.clear')}}</button></div>
 </form>
 @if(loading()){<p role="status">{{i18n.t('executions.loading')}}</p>}
 @else if(failure()){<syn-state state="unavailable" [title]="i18n.t('executions.error.unavailable.title')" [message]="i18n.t('executions.error.unavailable.message')"/>}
 @else if(!result()?.items?.length){<syn-state state="empty" [title]="i18n.t('executions.emptyTitle')" [message]="i18n.t('executions.empty')"/>}
 @else {<div class="results">@for(item of result()!.items;track item.execution_id){<button type="button" class="card execution-row" (click)="open(item)"><span><strong class="technical">{{item.execution_id}}</strong><small>{{i18n.formatDate(item.started_at,{dateStyle:'medium',timeStyle:'short'})}}</small></span><span><strong>{{publicState(item)}}</strong><small>{{i18n.t('executions.persistedState')}}: {{item.status}}</small></span><span><strong>{{item.source||'-'}}</strong><small>{{item.file_types.join(', ')||'-'}}</small></span><span><strong>{{i18n.formatNumber(item.rows_read)}}</strong><small>{{i18n.t('executions.count.rowsRead')}}</small></span></button>}</div><syn-pagination [page]="result()!.pagination.page" [pages]="result()!.pagination.pages" (pageChange)="load($event)"/>}
</section>`,
  styles: ['.execution-catalog{display:grid;gap:var(--syn-space-5)}.filters{display:grid;gap:var(--syn-space-3);grid-template-columns:repeat(auto-fit,minmax(12rem,1fr))}.filters label{display:grid;gap:.35rem}.actions{align-items:end;display:flex;gap:var(--syn-space-2)}.results{display:grid;gap:var(--syn-space-2)}.execution-row{align-items:center;background:var(--syn-surface);color:inherit;display:grid;grid-template-columns:minmax(15rem,2fr) repeat(3,minmax(8rem,1fr));text-align:left;width:100%}.execution-row span{display:grid;gap:.25rem}.execution-row small{color:var(--color-muted)}@media(max-width:767px){.execution-row{grid-template-columns:1fr 1fr}.filters{grid-template-columns:1fr}}']
})
export class ExecutionSearchComponent implements OnInit {
 readonly i18n=inject(I18nService);private readonly api=inject(ExecutionService);private readonly route=inject(ActivatedRoute);private readonly router=inject(Router);
 readonly result=signal<Page<ExecutionCatalogItem>|null>(null);readonly loading=signal(true);readonly failure=signal<ApiFailure|null>(null);
 readonly executionId=signal('');readonly organizationId=signal('');readonly status=signal('');readonly lifecycle=signal('');readonly source=signal('');readonly fileType=signal('');readonly dateFrom=signal('');readonly dateTo=signal('');readonly sort=signal<'oldest'|'newest'>('newest');
 ngOnInit():void{const q=this.route.snapshot.queryParamMap;this.executionId.set(q.get('execution_id')??'');this.organizationId.set(q.get('organization_id')??'');this.status.set(q.get('status')??'');this.lifecycle.set(q.get('lifecycle')??'');this.source.set(q.get('source')??'');this.fileType.set(q.get('file_type')??'');this.dateFrom.set(q.get('date_from')??'');this.dateTo.set(q.get('date_to')??'');this.sort.set(q.get('sort')==='oldest'?'oldest':'newest');this.load(this.page(q.get('page')))}
 apply(event:Event):void{event.preventDefault();this.load(1)}
 load(page:number):void{const filters=this.filters(page);void this.router.navigate([],{relativeTo:this.route,queryParams:this.query(filters),replaceUrl:true});this.loading.set(true);this.failure.set(null);this.api.list(filters).subscribe({next:value=>{this.result.set(value);this.loading.set(false)},error:(error:ApiFailure)=>{this.failure.set(error);this.loading.set(false)}})}
 clear():void{this.executionId.set('');this.organizationId.set('');this.status.set('');this.lifecycle.set('');this.source.set('');this.fileType.set('');this.dateFrom.set('');this.dateTo.set('');this.sort.set('newest');this.load(1)}
 open(item:ExecutionCatalogItem):void{void this.router.navigate(['/executions',item.execution_id],{queryParams:{from:this.router.url}})}
 publicState(item:ExecutionCatalogItem):string{return this.i18n.t(`executions.lifecycle.${item.lifecycle}` as never)}
 private filters(page:number):ExecutionCatalogFilters{return {executionId:this.executionId().trim()||undefined,organizationId:this.organizationId().trim()||undefined,status:this.status().trim()||undefined,lifecycle:this.lifecycle()||undefined,source:this.source().trim()||undefined,fileType:this.fileType().trim()||undefined,dateFrom:this.dateFrom()||undefined,dateTo:this.dateTo()||undefined,page,pageSize:20,sort:this.sort()}}
 private query(f:ExecutionCatalogFilters):Record<string,string|number|null>{return {execution_id:f.executionId??null,organization_id:f.organizationId??null,status:f.status??null,lifecycle:f.lifecycle??null,source:f.source??null,file_type:f.fileType??null,date_from:f.dateFrom??null,date_to:f.dateTo??null,page:f.page,sort:f.sort}}
 private page(value:string|null):number{const parsed=Number(value??1);return Number.isInteger(parsed)&&parsed>0?parsed:1}
}
