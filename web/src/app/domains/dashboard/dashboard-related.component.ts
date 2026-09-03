import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { DashboardService } from './dashboard.service';
import { I18nService } from '../../shared/i18n/i18n.service';
import { StateComponent, ResponsiveTableComponent } from '../../shared/ui/ui-kit';

type Entity = 'executions' | 'workorders' | 'pending-items';
@Component({
  imports: [RouterLink, StateComponent, ResponsiveTableComponent],
  template: `<section aria-labelledby="related-title"><header class="page-header"><div><p class="eyebrow">{{ i18n.t('dashboard.eyebrow') }}</p><h1 id="related-title">{{ title() }}</h1><p class="page-subtitle">{{ i18n.t('dashboard.relatedContext') }}</p></div><a routerLink="/dashboard" [queryParams]="context">{{ i18n.t('dashboard.back') }}</a></header>
  @if (loading()) { <syn-state state="loading" [title]="i18n.t('dashboard.loadingTitle')" [message]="i18n.t('dashboard.loading')" /> }
  @else if (error()) { <syn-state state="unavailable" [title]="i18n.t('dashboard.unavailableTitle')" [message]="i18n.t('dashboard.unavailable')" /> }
  @else if (!items().length) { <syn-state state="success" [title]="i18n.t('dashboard.emptyTitle')" [message]="i18n.t('dashboard.empty')" /> }
  @else { <section class="card"><h2>{{ i18n.t('dashboard.relatedRecords') }}</h2><syn-responsive-table><table><thead><tr><th>{{ i18n.t('dashboard.identifier') }}</th><th>{{ i18n.t('dashboard.status') }}</th><th>{{ i18n.t('dashboard.occurredAt') }}</th></tr></thead><tbody>@for(item of items();track item.identifier){<tr><td class="technical">{{ item.identifier }}</td><td>{{ item.status }}</td><td>{{ i18n.formatDate(item.occurred_at,{dateStyle:'short',timeStyle:'short'}) }}</td></tr>}</tbody></table></syn-responsive-table></section> }
  </section>`,
  styles: ['.page-header{align-items:center;border-bottom:1px solid var(--syn-border);padding-bottom:16px}.page-header a{font-weight:600}.card{margin-top:20px}@media(max-width:767px){.page-header{align-items:flex-start}.page-header a{margin-top:12px}}']
})
export class DashboardRelatedComponent implements OnInit {
  readonly i18n=inject(I18nService); private route=inject(ActivatedRoute); private router=inject(Router); private service=inject(DashboardService);
  readonly items=signal<Array<{identifier:string;status:string;occurred_at:string}>>([]); readonly loading=signal(true); readonly error=signal(false);
  readonly entity=(this.route.snapshot.paramMap.get('entity') ?? 'executions') as Entity;
  readonly context={organization:this.route.snapshot.queryParamMap.get('organization'),dateFrom:this.route.snapshot.queryParamMap.get('dateFrom'),dateTo:this.route.snapshot.queryParamMap.get('dateTo')};
  title():string{return this.i18n.t(this.entity==='executions'?'dashboard.executions':this.entity==='workorders'?'dashboard.workorders':'dashboard.pending');}
  ngOnInit():void{if(!['executions','workorders','pending-items'].includes(this.entity)){void this.router.navigateByUrl('/dashboard');return;}this.service.getRelated(this.entity,{organizationId:this.context.organization??'',dateFrom:this.context.dateFrom??'',dateTo:this.context.dateTo??''}).subscribe({next:value=>{this.items.set(value.items);this.loading.set(false);},error:()=>{this.error.set(true);this.loading.set(false);}});}
}
