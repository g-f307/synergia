import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { PaginationComponent, StateComponent } from '../../shared/ui/ui-kit';
import { ExecutionCatalogFilters, ExecutionCatalogItem } from './execution.models';
import { ExecutionService } from './execution.service';
import { Subscription } from 'rxjs';
import { EXECUTION_OUTCOMES, ExecutionFrame, ExecutionScopeFilters, ExecutionOutcome } from './execution.models';
import { ExecutionScopeComponent } from './execution-scope.component';
import { executionStatusLabel, executionUrlParams, filtersFromAggregate, filtersFromParams, normalizedExecutionFilters, outcomeLabel } from './execution-presentation';
import { profileInput } from '../../shared/i18n/profile-time';

@Component({
  imports: [PaginationComponent, StateComponent, ExecutionScopeComponent],
  template: `
<section class="execution-catalog" aria-labelledby="execution-catalog-title">
 <h1 id="execution-catalog-title" class="sr-only">{{i18n.t('executions.catalogTitle')}}</h1>
 <header class="results-heading"><div><h2>{{i18n.t('executions.resultsTitle')}}</h2>@if(summary();as current){<p>{{i18n.t('queries.total',{count:i18n.formatNumber(current.total)})}}</p>}</div>@if(summary();as current){<time [attr.datetime]="current.generated_at">{{i18n.formatDate(current.generated_at,{dateStyle:'short',timeStyle:'short'})}}</time>}</header>
 <details class="catalog-filters">
  <summary><span class="filter-summary-title"><span class="filter-toggle-icon" aria-hidden="true">▶</span>{{i18n.t('executions.filtersTitle')}}</span><small>{{i18n.t('executions.catalogHelp')}}</small></summary>
  <form class="filters" (submit)="apply($event)">
   <div class="filter-field"><label for="execution-id">{{i18n.t('executions.id')}}</label><input id="execution-id" name="execution_id" [value]="executionId()" (input)="executionId.set($any($event.target).value)" autocomplete="off"></div>
   <div class="filter-field"><label for="execution-organization">{{i18n.t('executions.organization')}}</label><input id="execution-organization" name="organization_id" [value]="organizationId()" (input)="organizationId.set($any($event.target).value)" autocomplete="off"></div>
   <div class="filter-field"><label for="execution-status">{{i18n.t('executions.persistedState')}}</label><input id="execution-status" name="status" [value]="status()" (input)="status.set($any($event.target).value)" autocomplete="off"></div>
   <div class="filter-field"><label for="execution-outcome">{{i18n.t('executions.scope.status')}}</label><select id="execution-outcome" name="outcome" [value]="outcome()" (change)="outcome.set($any($event.target).value);lifecycle.set('')"><option value="">{{i18n.t('executions.all')}}</option>@for(value of outcomes;track value){<option [value]="value">{{label(value)}}</option>}</select></div>
   <div class="filter-field"><label for="execution-source">{{i18n.t('executions.source')}}</label><input id="execution-source" name="source" [value]="source()" (input)="source.set($any($event.target).value)" autocomplete="off"></div>
   <div class="filter-field"><label for="execution-file-type">{{i18n.t('executions.fileType')}}</label><input id="execution-file-type" name="file_type" [value]="fileType()" (input)="fileType.set($any($event.target).value)" autocomplete="off"></div>
   <div class="filter-field"><label for="execution-date-from">{{i18n.t('executions.dateFrom')}}</label><input id="execution-date-from" [attr.aria-invalid]="filterError()?true:null" [attr.aria-describedby]="filterError()?'execution-period-error':null" name="date_from" type="datetime-local" step="1" [value]="dateFrom()" (input)="dateFrom.set($any($event.target).value)"></div>
   <div class="filter-field"><label for="execution-date-to">{{i18n.t('executions.dateTo')}}</label><input id="execution-date-to" [attr.aria-invalid]="filterError()?true:null" [attr.aria-describedby]="filterError()?'execution-period-error':null" name="date_to" type="datetime-local" step="1" [value]="dateTo()" (input)="dateTo.set($any($event.target).value)"></div>
   <div class="filter-field"><label for="execution-sort">{{i18n.t('executions.sort')}}</label><select id="execution-sort" name="sort" [value]="sort()" (change)="sort.set($any($event.target).value)"><option value="newest">{{i18n.t('executions.newest')}}</option><option value="oldest">{{i18n.t('executions.oldest')}}</option></select></div>
   <div class="actions"><button type="submit">{{i18n.t('executions.filter')}}</button><button type="button" class="secondary" (click)="clear()">{{i18n.t('executions.clear')}}</button></div>
  </form>
 </details>
 @if(filterError()){<p id="execution-period-error" role="alert">{{filterError()}}</p>}
 <div class="catalog-content">
  @if(summary();as current){
   <syn-execution-scope [summary]="current"/>
   <dl class="outcome-totals">@for(value of outcomes;track value){<div [attr.data-outcome]="value"><dt>{{label(value)}}</dt><dd>{{i18n.formatNumber(current.by_outcome[value])}}</dd></div>}</dl>
  }
  @if(failure()&&result()){<p role="status">{{i18n.t('executions.stale')}}</p>}
  @if(loading()&&result()){<p role="status">{{i18n.t('executions.refreshing')}}</p>}
  @if(loading()&&!result()){<p class="loading" role="status">{{i18n.t('executions.loading')}}</p>}
  @else if(failure()&&!result()){
   @if(failure()?.kind==='forbidden'||failure()?.kind==='unauthorized'){<syn-state state="forbidden" [title]="i18n.t('executions.error.forbidden.title')" [message]="i18n.t('executions.error.forbidden.message')"/>}
   @else{<syn-state state="unavailable" [title]="i18n.t('executions.error.unavailable.title')" [message]="i18n.t('executions.error.unavailable.message')"/>}
  }
  @else if(!result()?.items?.length){<syn-state state="empty" [title]="i18n.t('executions.emptyTitle')" [message]="i18n.t('executions.empty')"/>}
  @else {
   <div class="results">@for(item of result()!.items;track item.execution_id){
    <button type="button" class="execution-row" (click)="open(item)">
     <span class="execution-identity"><strong class="technical">{{item.execution_id}}</strong><small>{{i18n.formatDate(item.started_at,{dateStyle:'medium',timeStyle:'short'})}}</small></span>
     <span><strong class="status-pill" [attr.data-state]="item.outcome">{{publicState(item)}}</strong><small [attr.title]="item.status">{{technicalState(item)}}</small></span>
     <span><strong>{{item.source||'-'}}</strong><small>{{item.file_types.join(', ')||'-'}}</small></span>
     <span class="row-metric"><strong>{{i18n.formatNumber(item.rows_read)}}</strong><small>{{i18n.t('executions.count.rowsRead')}}</small></span>
     <span class="row-chevron" aria-hidden="true">›</span>
    </button>
   }</div>
   <syn-pagination [page]="result()!.pagination.page" [pages]="result()!.pagination.pages" (pageChange)="load($event)"/>
  }
 </div>
</section>`,
  styles: [`
  :host{display:block;height:100%;min-height:0}.execution-catalog{--line:color-mix(in srgb,var(--syn-text) 9%,transparent);background:var(--syn-bg-card);border:1px solid var(--line);border-radius:28px;height:100%;min-height:0;overflow-x:hidden;overflow-y:auto;padding:clamp(20px,2.5vw,34px);scrollbar-gutter:stable}.sr-only{clip:rect(0,0,0,0);clip-path:inset(50%);height:1px;overflow:hidden;position:absolute;white-space:nowrap;width:1px}.catalog-filters{background:var(--syn-bg);border:1px solid var(--line);border-radius:14px;margin-bottom:18px}.catalog-filters summary{align-items:center;cursor:pointer;display:flex;gap:16px;justify-content:space-between;list-style:none;padding:13px 16px}.catalog-filters summary::-webkit-details-marker{display:none}.filter-summary-title{align-items:center;display:inline-flex;font-size:.9rem;font-weight:700;gap:8px}.filter-toggle-icon{font-size:.7rem;line-height:1;transition:transform var(--syn-transition)}.catalog-filters[open] .filter-toggle-icon{transform:rotate(90deg)}.catalog-filters summary small{color:var(--syn-text-secondary);font-size:.76rem}.filters{border-top:1px solid var(--line);display:grid;gap:14px;grid-template-columns:repeat(3,minmax(0,1fr));padding:18px 16px}.filter-field{display:grid;gap:7px;min-width:0}.filters label{font-size:.76rem;font-weight:600}.filters input,.filters select{background:var(--syn-bg-card);color:var(--syn-text);min-height:44px;width:100%}.actions{align-items:end;display:flex;gap:8px;grid-column:1/-1;justify-content:flex-end;margin-top:5px}.actions button{border-radius:999px}.catalog-content{display:grid;gap:16px;min-height:0;overflow:visible;padding-right:4px}.loading{color:var(--syn-text-secondary);margin:0}.results-heading{align-items:center;display:flex;justify-content:space-between;margin-bottom:14px}.results-heading h2,.results-heading p{margin:0}.results-heading h2{font-size:1rem}.results-heading p,.results-heading time{color:var(--syn-text-secondary);font-size:.76rem}.results{border:1px solid var(--line);border-radius:18px;display:grid;min-height:0;overflow:visible}.execution-row{align-items:center;background:var(--syn-bg-card);border:0;border-bottom:1px solid var(--line);border-radius:0;color:var(--syn-text);display:grid;gap:18px;grid-template-columns:minmax(14rem,1.8fr) minmax(8rem,1fr) minmax(7rem,.8fr) minmax(6rem,.55fr) 20px;min-height:86px;padding:17px 20px;text-align:left;transition:background var(--syn-transition),border-color var(--syn-transition);width:100%}.execution-row:last-child{border-bottom:0}.execution-row:hover{background:color-mix(in srgb,var(--syn-primary) 7%,var(--syn-bg-card))}.execution-row:focus-visible{outline:3px solid color-mix(in srgb,var(--syn-primary) 34%,transparent);outline-offset:-3px}.execution-row span{display:grid;gap:5px;min-width:0}.execution-row strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.execution-row small{color:var(--syn-text-secondary);font-size:.75rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.status-pill{border:1px solid var(--line);border-radius:999px;font-size:.76rem;padding:5px 9px;width:max-content}.status-pill[data-state=completed]{background:color-mix(in srgb,#39805f 13%,var(--syn-bg-card));border-color:color-mix(in srgb,#39805f 30%,transparent);color:color-mix(in srgb,#39805f 76%,var(--syn-text))}.status-pill[data-state=active]{background:color-mix(in srgb,#5577b8 13%,var(--syn-bg-card));color:color-mix(in srgb,#5577b8 74%,var(--syn-text))}.status-pill[data-state=partial]{background:color-mix(in srgb,#b07828 14%,var(--syn-bg-card));color:color-mix(in srgb,#b07828 78%,var(--syn-text))}.status-pill[data-state=failed]{background:color-mix(in srgb,#b84242 13%,var(--syn-bg-card));color:color-mix(in srgb,#b84242 76%,var(--syn-text))}.row-metric{text-align:right}.row-metric strong{font-family:LGEIHeadline,sans-serif;font-size:1.25rem}.row-chevron{color:var(--syn-text-secondary);font-size:1.5rem;text-align:right}
  @media(max-width:900px){.filters{grid-template-columns:repeat(2,minmax(0,1fr))}.execution-row{grid-template-columns:minmax(12rem,1.5fr) 1fr 1fr 20px}.row-metric{display:none!important}}
  @media(max-width:600px){.execution-catalog{border-radius:20px;padding:18px}.catalog-filters summary small{display:none}.filters{grid-template-columns:1fr}.actions{display:grid;grid-template-columns:1fr 1fr}.execution-row{gap:10px 12px;grid-template-areas:"identity chevron" "status chevron" "source chevron";grid-template-columns:minmax(0,1fr) auto;min-height:auto;padding:16px}.execution-identity{grid-area:identity}.execution-row>span:nth-child(2){grid-area:status}.execution-row>span:nth-child(3){grid-area:source}.row-chevron{align-self:center;grid-area:chevron}.execution-identity strong{white-space:normal}}
  `, `.outcome-totals{display:flex;flex-wrap:wrap;gap:12px 24px;margin:0;padding:4px 0 14px;border-bottom:1px solid var(--syn-border)}.outcome-totals div{display:grid;gap:4px}.outcome-totals dt{font-size:.75rem;color:var(--syn-text-secondary)}.outcome-totals dd{margin:0;font-variant-numeric:tabular-nums;font-weight:700}`]
})
export class ExecutionSearchComponent implements OnInit, OnDestroy {
 readonly i18n=inject(I18nService);private readonly api=inject(ExecutionService);private readonly route=inject(ActivatedRoute);private readonly router=inject(Router);
 readonly frame=signal<ExecutionFrame|null>(null);readonly result=computed(()=>this.frame()?.page??null);readonly summary=computed(()=>this.frame()?.summary??null);readonly loading=signal(true);readonly failure=signal<ApiFailure|null>(null);
 readonly executionId=signal('');readonly organizationId=signal('');readonly status=signal('');readonly lifecycle=signal('');readonly source=signal('');readonly fileType=signal('');readonly dateFrom=signal('');readonly dateTo=signal('');readonly sort=signal<'oldest'|'newest'>('newest');
 readonly outcome=signal<ExecutionOutcome|''>(''); readonly outcomes=EXECUTION_OUTCOMES; readonly filterError=signal('');
 private request?:Subscription; private routeRequest?:Subscription; private requested:ExecutionScopeFilters={}; private requestKey=''; private invalidRoute=false;
 ngOnInit():void{this.routeRequest=this.route.queryParamMap.subscribe(q=>{try{
  const filters=filtersFromParams(q,this.i18n.timezone());const sort=q.get('sort')==='oldest'?'oldest':'newest';const page=this.page(q.get('page'));
  this.invalidRoute=false;this.filterError.set('');if(this.key(filters,page,sort)===this.requestKey)return;
  this.executionId.set(filters.executionId??'');this.organizationId.set(filters.organizationId??'');this.status.set(filters.status??'');this.lifecycle.set(filters.lifecycle??'');this.outcome.set(filters.outcome??'');this.source.set(filters.source??'');this.fileType.set(filters.fileType??'');
  this.dateFrom.set(profileInput(filters.dateFrom,this.i18n.timezone()));this.dateTo.set(profileInput(filters.dateTo,this.i18n.timezone()));this.sort.set(sort);this.load(page,filters,sort);
 }catch{this.invalidRoute=true;this.requestKey='';this.request?.unsubscribe();this.filterError.set(this.i18n.t('executions.invalidPeriod'));this.loading.set(false)}})}
 ngOnDestroy():void{this.request?.unsubscribe();this.routeRequest?.unsubscribe()}
 apply(event:Event):void{event.preventDefault();try{const f=this.filters(1);this.invalidRoute=false;this.filterError.set('');this.load(1,f,f.sort)}catch{this.filterError.set(this.i18n.t('executions.invalidPeriod'))}}
 load(page:number,scope:ExecutionScopeFilters=this.summary()?filtersFromAggregate(this.summary()!):this.requested,sort:'oldest'|'newest'=this.result()?.sort==='oldest'?'oldest':this.sort()):void{
  if(this.invalidRoute)return;this.request?.unsubscribe();this.requested=scope;this.requestKey=this.key(scope,page,sort);this.loading.set(true);this.failure.set(null);
  this.request=this.api.frame({...scope,page,pageSize:20,sort}).subscribe({next:value=>{this.frame.set(value);this.loading.set(false);const effective=filtersFromAggregate(value.summary);this.requestKey=this.key(effective,page,sort);if(!this.router.getCurrentNavigation())void this.router.navigate([],{relativeTo:this.route,queryParams:{...executionUrlParams(effective),page,sort},replaceUrl:true})},error:(error:ApiFailure)=>{if(error.kind==='forbidden'||error.kind==='unauthorized')this.frame.set(null);this.failure.set(error);this.loading.set(false)}})
 }
 clear():void{this.executionId.set('');this.organizationId.set('');this.status.set('');this.lifecycle.set('');this.outcome.set('');this.source.set('');this.fileType.set('');this.dateFrom.set('');this.dateTo.set('');this.sort.set('newest');this.invalidRoute=false;this.filterError.set('');this.load(1,{},'newest')}
 open(item:ExecutionCatalogItem):void{void this.router.navigate(['/executions',item.execution_id],{queryParams:{from:this.router.url}})}
 publicState(item:ExecutionCatalogItem):string{return this.label(item.outcome)}
 technicalState(item:ExecutionCatalogItem):string{return this.i18n.t(executionStatusLabel(item.status))}
 label(value:string):string{return this.i18n.t(outcomeLabel(value))}
 private filters(page:number):ExecutionCatalogFilters{const date=(bound:'start'|'end')=>{const old=bound==='start'?this.requested.dateFrom:this.requested.dateTo;const value=bound==='start'?this.dateFrom():this.dateTo();return value===profileInput(old,this.i18n.timezone())?old:value};return {...normalizedExecutionFilters({executionId:this.executionId(),organizationId:this.organizationId(),status:this.status(),lifecycle:(this.outcome()||undefined)!==this.requested.outcome?undefined:this.requested.lifecycle,outcome:this.outcome()||undefined,source:this.source(),fileType:this.fileType(),dateFrom:date('start'),dateTo:date('end')},this.i18n.timezone()),page,pageSize:20,sort:this.sort()}}
 private key(f:ExecutionScopeFilters,page:number,sort:string):string{return JSON.stringify({...executionUrlParams(f),page,sort})}
 private page(value:string|null):number{const parsed=Number(value??1);return Number.isInteger(parsed)&&parsed>0?parsed:1}
}
