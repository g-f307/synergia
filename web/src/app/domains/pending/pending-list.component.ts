import { Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, ParamMap, Router, RouterLink } from '@angular/router';
import { catchError, map, of, switchMap, tap } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { PaginationComponent, ResponsiveTableComponent, StateComponent, UiState } from '../../shared/ui/ui-kit';
import { PendingFilters, PendingItem, PendingPage, PendingSort } from './pending.models';
import { PENDING_PRIORITY_KEYS, PENDING_STATUS_KEYS } from './pending-labels';
import { PendingService } from './pending.service';
import { pendingIsStale, pendingKind, pendingPageIsPartial } from './pending-state';

@Component({
  imports: [PaginationComponent, ResponsiveTableComponent, RouterLink, StateComponent],
  template: `
    <section class="pending-page" aria-labelledby="pending-title">
      <header class="page-header"><div><p class="eyebrow">{{ i18n.t('pending.eyebrow') }}</p><h1 id="pending-title">{{ i18n.t('pending.title') }}</h1><p class="page-subtitle">{{ i18n.t('pending.help') }}</p></div></header>
      <form class="card filters" (submit)="submit($event)">
        <label>{{ i18n.t('pending.status') }}<select [value]="status()" (change)="status.set($any($event.target).value)"><option value="open">{{ i18n.t('pending.status.open') }}</option><option value="resolved">{{ i18n.t('pending.status.resolved') }}</option><option value="cancelled">{{ i18n.t('pending.status.cancelled') }}</option><option value="">{{ i18n.t('pending.status.all') }}</option></select></label>
        <label>{{ i18n.t('pending.category') }}<input type="search" [value]="category()" (input)="category.set($any($event.target).value)"></label>
        <label>{{ i18n.t('pending.priority') }}<select [value]="priority()" (change)="priority.set($any($event.target).value)"><option value="">{{ i18n.t('pending.any') }}</option><option value="critical">{{ i18n.t('pending.priority.critical') }}</option><option value="high">{{ i18n.t('pending.priority.high') }}</option><option value="normal">{{ i18n.t('pending.priority.normal') }}</option><option value="low">{{ i18n.t('pending.priority.low') }}</option></select></label>
        <label>{{ i18n.t('pending.area') }}<input type="search" [value]="area()" (input)="area.set($any($event.target).value)"></label>
        <label>{{ i18n.t('pending.identifierType') }}<select [value]="identifierType()" (change)="identifierType.set($any($event.target).value)"><option value="workorder">Workorder</option><option value="lot">{{ i18n.t('queries.lot') }}</option><option value="serial">Serial</option><option value="execution">{{ i18n.t('queries.execution') }}</option></select></label>
        <label>{{ i18n.t('pending.identifier') }}<input type="search" class="technical" [value]="identifier()" (input)="identifier.set($any($event.target).value)"></label>
        <label>{{ i18n.t('queries.sort') }}<select [value]="sort()" (change)="sort.set($any($event.target).value)"><option value="oldest">{{ i18n.t('pending.sort.oldest') }}</option><option value="newest">{{ i18n.t('pending.sort.newest') }}</option><option value="priority">{{ i18n.t('pending.sort.priority') }}</option><option value="category">{{ i18n.t('pending.sort.category') }}</option></select></label>
        <label>{{ i18n.t('queries.pageSize') }}<select [value]="pageSize()" (change)="pageSize.set(+$any($event.target).value)"><option value="10">10</option><option value="25">25</option><option value="50">50</option></select></label>
        <button type="submit" [disabled]="loading()">{{ i18n.t('pending.apply') }}</button>
      </form>

      @if (loading()) { <syn-state state="loading" [title]="i18n.t('pending.loadingTitle')" [message]="i18n.t('pending.loading')" /> }
      @if (failureState(); as state) { <syn-state [state]="state" [title]="failureTitle()" [message]="failureMessage()" /> }
      @if (result(); as current) {
        @if (isPartial(current)) { <syn-state state="partial" [title]="i18n.t('pending.partialTitle')" [message]="i18n.t('pending.partial')" /> }
        @if (isStale(current)) { <syn-state state="stale" [title]="i18n.t('queries.staleTitle')" [message]="i18n.t('queries.stale')" /> }
        <section class="card results">
          <header><div><h2>{{ i18n.t('pending.queue') }}</h2><p>{{ i18n.t('queries.total', { count: i18n.formatNumber(current.pagination.total) }) }}</p></div><time [attr.datetime]="current.generated_at">{{ i18n.formatDate(current.generated_at,{dateStyle:'short',timeStyle:'short'}) }}</time></header>
          @if (!current.items.length) { <syn-state state="empty" [title]="i18n.t('pending.emptyTitle')" [message]="i18n.t('pending.empty')" /> }
          @else { <syn-responsive-table><table><thead><tr><th>{{ i18n.t('pending.category') }}</th><th>{{ i18n.t('pending.kind') }}</th><th>Workorder</th><th>{{ i18n.t('pending.priority') }}</th><th>{{ i18n.t('pending.area') }}</th><th>{{ i18n.t('pending.status') }}</th><th>{{ i18n.t('queries.updatedAt') }}</th></tr></thead><tbody>@for(item of current.items;track item.id){<tr><td><a [routerLink]="['/pending-items',item.id]" [queryParams]="{from:currentUrl()}"><strong class="technical">{{ item.category }}</strong></a></td><td><span class="badge" [attr.data-pending-kind]="kind(item)">{{ kindLabel(item) }}</span></td><td class="technical">{{ item.workorder_number }}</td><td>{{ priorityLabel(item.priority) }}</td><td>{{ item.responsible_area || i18n.t('common.notAvailable') }}</td><td>{{ statusLabel(item.status) }}</td><td><time [attr.datetime]="item.updated_at">{{ i18n.formatDate(item.updated_at,{dateStyle:'short',timeStyle:'short'}) }}</time></td></tr>}</tbody></table></syn-responsive-table> }
          @if(current.pagination.pages){<syn-pagination [page]="current.pagination.page" [pages]="current.pagination.pages" (pageChange)="changePage($event)" />}
        </section>
      }
    </section>
  `,
  styles: ['.pending-page{display:grid;gap:var(--syn-space-5);max-width:82rem}.page-header{border-bottom:1px solid var(--syn-border);padding-bottom:var(--syn-space-4)}.filters{align-items:end;display:grid;gap:var(--syn-space-4);grid-template-columns:repeat(4,minmax(9rem,1fr))}.filters button{grid-column:4}.results{display:grid;gap:var(--syn-space-4)}.results>header{align-items:start;display:flex;justify-content:space-between}.results h2,.results p{margin:0}.badge[data-pending-kind=pre-release]{color:var(--syn-info)}.badge[data-pending-kind=post-release]{color:var(--syn-error)}.badge[data-pending-kind=technical]{color:var(--syn-attention)}.badge[data-pending-kind=partial]{color:var(--syn-partial)}@media(max-width:900px){.filters{grid-template-columns:1fr 1fr}.filters button{grid-column:1/-1}}@media(max-width:560px){.filters{grid-template-columns:1fr}}']
})
export class PendingListComponent {
  readonly i18n=inject(I18nService);private route=inject(ActivatedRoute);private router=inject(Router);private api=inject(PendingService);
  readonly status=signal('open');readonly category=signal('');readonly priority=signal('');readonly area=signal('');readonly identifierType=signal('workorder');readonly identifier=signal('');readonly sort=signal<PendingSort>('oldest');readonly pageSize=signal(25);readonly loading=signal(true);readonly result=signal<PendingPage|null>(null);readonly failure=signal<ApiFailure|null>(null);
  readonly failureState=computed<UiState|null>(()=>{const kind=this.failure()?.kind;if(!kind||kind==='unauthorized')return null;if(kind==='forbidden')return 'forbidden';if(kind==='unavailable')return 'unavailable';return 'error'});
  constructor(){this.route.queryParamMap.pipe(tap(params=>this.readParams(params)),switchMap(params=>this.api.list(this.filters(params)).pipe(map(value=>({value,failure:null})),catchError((failure:ApiFailure)=>of({value:null,failure})))),takeUntilDestroyed()).subscribe(({value,failure})=>{this.result.set(value);this.failure.set(failure);this.loading.set(false)})}
  submit(event:Event):void{event.preventDefault();this.navigate(1)}changePage(page:number):void{this.navigate(page)}currentUrl():string{return this.router.url}kind(item:PendingItem){return pendingKind(item)}
  kindLabel(item:PendingItem):string{const kind=pendingKind(item);if(kind==='pre-release')return this.i18n.t('pending.kind.preRelease');if(kind==='post-release')return this.i18n.t('pending.kind.postRelease');if(kind==='technical')return this.i18n.t('pending.kind.technical');if(kind==='partial')return this.i18n.t('pending.kind.partial');return this.i18n.t('pending.kind.operational')}
  priorityLabel(priority:string):string{return this.i18n.t(PENDING_PRIORITY_KEYS[priority]??'pending.priority.normal')}
  statusLabel(status:string):string{return this.i18n.t(PENDING_STATUS_KEYS[status]??'pending.status.open')}
  isPartial(page:PendingPage):boolean{return pendingPageIsPartial(page)}isStale(page:PendingPage):boolean{return pendingIsStale(page.generated_at)}
  failureTitle():string{return this.i18n.t(this.failure()?.kind==='forbidden'?'pending.forbiddenTitle':this.failure()?.kind==='unavailable'?'pending.unavailableTitle':'pending.errorTitle')}
  failureMessage():string{return this.i18n.t(this.failure()?.kind==='forbidden'?'pending.forbidden':this.failure()?.kind==='unavailable'?'pending.unavailable':'pending.error')}
  private readParams(params:ParamMap):void{this.status.set(params.get('status')??'open');this.category.set(params.get('category')??'');this.priority.set(params.get('priority')??'');this.area.set(params.get('area')??'');this.sort.set(this.validSort(params.get('sort')));this.pageSize.set(this.positive(params.get('pageSize'),25,[10,25,50]));for(const [type,key] of [['workorder','workorder'],['lot','lot'],['serial','serial'],['execution','execution']] as const){const value=params.get(key);if(value){this.identifierType.set(type);this.identifier.set(value);break}}this.loading.set(true);this.result.set(null);this.failure.set(null)}
  private filters(params:ParamMap):PendingFilters{const identifier=this.identifier();return{status:this.status(),category:this.category(),priority:this.priority(),responsibleArea:this.area(),workorderNumber:this.identifierType()==='workorder'?identifier:'',lotNumber:this.identifierType()==='lot'?identifier:'',serialNumber:this.identifierType()==='serial'?identifier:'',executionId:this.identifierType()==='execution'?identifier:'',page:this.positive(params.get('page'),1),pageSize:this.pageSize(),sort:this.sort()}}
  private navigate(page:number):void{const identifier=this.identifier();void this.router.navigate([],{relativeTo:this.route,queryParams:{status:this.status()||null,category:this.category()||null,priority:this.priority()||null,area:this.area()||null,workorder:this.identifierType()==='workorder'&&identifier||null,lot:this.identifierType()==='lot'&&identifier||null,serial:this.identifierType()==='serial'&&identifier||null,execution:this.identifierType()==='execution'&&identifier||null,page,pageSize:this.pageSize(),sort:this.sort()}})}
  private validSort(value:string|null):PendingSort{return value==='newest'||value==='category'||value==='priority'?value:'oldest'}private positive(value:string|null,fallback:number,allowed?:number[]):number{const parsed=Number(value);return Number.isInteger(parsed)&&parsed>0&&(!allowed||allowed.includes(parsed))?parsed:fallback}
}
