import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { StateComponent, UiState } from '../../shared/ui/ui-kit';
import { ApprovalRequest, PendingItem } from './pending.models';
import { SessionService } from '../../core/session.service';
import { PENDING_PRIORITY_KEYS, PENDING_STATUS_KEYS } from './pending-labels';
import { PendingService } from './pending.service';
import { pendingIsPartial, pendingIsStale, pendingKind } from './pending-state';

const APPROVAL_STATE_KEYS: Record<string, TranslationKey> = {
  draft: 'approval.state.draft', submitted: 'approval.state.submitted',
  in_review: 'approval.state.inReview', approved: 'approval.state.approved',
  rejected: 'approval.state.rejected', returned: 'approval.state.returned'
};
const APPROVAL_EVENT_KEYS: Record<string, TranslationKey> = {
  created: 'approval.event.created', submitted: 'approval.event.submitted',
  assigned: 'approval.event.assigned', reassigned: 'approval.event.reassigned',
  approved: 'approval.event.approved', rejected: 'approval.event.rejected',
  returned: 'approval.event.returned', resubmitted: 'approval.event.resubmitted'
};

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
        <section class="card approval" aria-labelledby="approval-title">
          <h2 id="approval-title">{{ i18n.t('approval.title') }}</h2>
          <p>{{ i18n.t('approval.automaticNotice') }}</p>
          @if(approval();as request){
            <dl><div><dt>{{ i18n.t('approval.state') }}</dt><dd><span class="badge">{{ approvalLabel('state',request.state) }}</span></dd></div><div><dt>{{ i18n.t('approval.group') }}</dt><dd>{{ request.review_group }}</dd></div><div><dt>{{ i18n.t('approval.assignee') }}</dt><dd class="technical">{{ request.assignee_user_id || i18n.t('common.notAvailable') }}</dd></div><div><dt>{{ i18n.t('approval.policy') }}</dt><dd class="technical">{{ request.policy_key }} v{{ request.policy_version }}</dd></div></dl>
            @if(session.hasPermission('approval.assign')&&(request.state==='submitted'||request.state==='in_review')){<div class="decision-form"><label>{{ i18n.t('approval.assignee') }}<input #assignee type="text"></label><label>{{ i18n.t('approval.justification') }}<textarea #assignmentReason></textarea></label><button type="button" (click)="assign(request,assignee.value,assignmentReason.value)">{{ i18n.t('approval.assign') }}</button></div>}
            @if(session.hasPermission('approval.decide')&&request.state==='in_review'&&request.assignee_user_id===session.profile()?.id){<div class="decision-form"><label>{{ i18n.t('approval.justification') }}<textarea #decisionReason></textarea></label><label class="consent"><input #consent type="checkbox">{{ i18n.t('approval.consent') }}</label><div class="actions"><button type="button" (click)="decide(request,'approve',decisionReason.value,consent.checked)">{{ i18n.t('approval.approve') }}</button><button class="secondary" type="button" (click)="decide(request,'reject',decisionReason.value)">{{ i18n.t('approval.reject') }}</button><button class="secondary" type="button" (click)="decide(request,'return',decisionReason.value)">{{ i18n.t('approval.return') }}</button></div></div>}
            @if(session.hasPermission('approval.submit')&&request.state==='returned'&&request.requester_user_id===session.profile()?.id){<div class="decision-form"><label>{{ i18n.t('approval.justification') }}<textarea #resubmitReason></textarea></label><button type="button" (click)="resubmit(request,resubmitReason.value)">{{ i18n.t('approval.resubmit') }}</button></div>}
            <h3>{{ i18n.t('approval.history') }}</h3><ol class="timeline">@for(event of request.history;track event.id){<li><strong>{{ approvalLabel('event',event.event_type) }}</strong><span>{{ i18n.formatDate(event.occurred_at,{dateStyle:'medium',timeStyle:'short'}) }}</span><span class="technical">{{ event.actor_user_id }}</span>@if(event.justification){<p>{{ event.justification }}</p>}</li>}</ol>
          }@else if(session.hasPermission('approval.submit')){<div class="decision-form"><label>{{ i18n.t('approval.justification') }}<textarea #submitReason></textarea></label><button type="button" (click)="submit(current.id,submitReason.value)">{{ i18n.t('approval.submit') }}</button></div>}@else{<p>{{ i18n.t('approval.none') }}</p>}
          @if(actionError()){<p class="error" role="alert">{{ actionError() }}</p>}
        </section>
      }
    </section>
  `,
  styles: ['.pending-detail{display:grid;gap:var(--syn-space-4);max-width:72rem}.pending-detail>button{width:max-content}header{align-items:start;border-left:4px solid var(--syn-primary);display:flex;gap:var(--syn-space-6);justify-content:space-between}header h1{margin-bottom:var(--syn-space-3)}dl{display:grid;gap:var(--syn-space-3);grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));margin:0;min-width:50%}dt{color:var(--syn-text-secondary);font-size:.875rem}dd{margin:0}.relationships{display:flex;flex-wrap:wrap;gap:var(--syn-space-4)}pre{background:var(--syn-bg);border:1px solid var(--syn-border);border-radius:var(--syn-radius-sm);overflow:auto;padding:var(--syn-space-4);white-space:pre-wrap}.badge[data-pending-kind=post-release]{color:var(--syn-error)}.badge[data-pending-kind=technical]{color:var(--syn-attention)}.badge[data-pending-kind=partial]{color:var(--syn-partial)}.approval{display:grid;gap:var(--syn-space-4)}.decision-form{border-top:1px solid var(--syn-border);display:grid;gap:var(--syn-space-3);padding-top:var(--syn-space-4)}.decision-form label{display:grid;gap:var(--syn-space-2)}textarea{min-height:6rem}.consent{align-items:center!important;display:flex!important}.actions{display:flex;flex-wrap:wrap;gap:var(--syn-space-2)}.timeline{display:grid;gap:var(--syn-space-3);list-style:none;padding:0}.timeline li{border-left:3px solid var(--syn-primary);display:grid;gap:var(--syn-space-1);padding-left:var(--syn-space-3)}.timeline span{color:var(--syn-text-secondary);font-size:.875rem}.error{color:var(--syn-error)}@media(max-width:700px){header{display:grid}dl{min-width:0}}']
})
export class PendingDetailComponent implements OnInit {
  readonly i18n=inject(I18nService);readonly session=inject(SessionService);private route=inject(ActivatedRoute);private router=inject(Router);private api=inject(PendingService);readonly item=signal<PendingItem|null>(null);readonly approval=signal<ApprovalRequest|null>(null);readonly loading=signal(true);readonly failure=signal<ApiFailure|null>(null);readonly actionError=signal('');
  readonly failureState=computed<UiState|null>(()=>{const kind=this.failure()?.kind;if(!kind||kind==='unauthorized')return null;if(kind==='not-found')return 'empty';if(kind==='forbidden')return 'forbidden';if(kind==='unavailable')return 'unavailable';return 'error'});
  ngOnInit():void{const id=Number(this.route.snapshot.paramMap.get('pendingId'));if(!Number.isSafeInteger(id)||id<=0){void this.router.navigateByUrl('/pending-items');return}this.api.detail(id).subscribe({next:value=>{this.item.set(value);this.loading.set(false);if(this.session.hasPermission('approval.read'))this.loadApproval(id)},error:(failure:ApiFailure)=>{this.failure.set(failure);this.loading.set(false)}})}
  private loadApproval(id:number):void{this.api.approval(id).subscribe({next:value=>this.approval.set(value),error:()=>this.approval.set(null)})}
  submit(id:number,reason:string):void{this.run(this.api.submitApproval(id,reason))}
  assign(request:ApprovalRequest,userId:string,reason:string):void{this.run(this.api.assignApproval(request,userId,reason))}
  decide(request:ApprovalRequest,action:'approve'|'reject'|'return',reason:string,consent=false):void{this.run(this.api.decideApproval(request,action,reason,consent))}
  resubmit(request:ApprovalRequest,reason:string):void{this.run(this.api.resubmitApproval(request,reason))}
  private run(operation:ReturnType<PendingService['submitApproval']>):void{this.actionError.set('');operation.subscribe({next:value=>this.approval.set(value),error:()=>this.actionError.set(this.i18n.t('approval.actionError'))})}
  approvalLabel(kind:'state'|'event',value:string):string{const key=(kind==='state'?APPROVAL_STATE_KEYS:APPROVAL_EVENT_KEYS)[value];return key?this.i18n.t(key):value}
  back():void{void this.router.navigateByUrl(this.returnUrl())}returnUrl():string{const from=this.route.snapshot.queryParamMap.get('from');return from?.startsWith('/pending-items?')||from==='/pending-items'?from:'/pending-items'}
  kind(item:PendingItem){return pendingKind(item)}kindLabel(item:PendingItem):string{const kind=pendingKind(item);if(kind==='pre-release')return this.i18n.t('pending.kind.preRelease');if(kind==='post-release')return this.i18n.t('pending.kind.postRelease');if(kind==='technical')return this.i18n.t('pending.kind.technical');if(kind==='partial')return this.i18n.t('pending.kind.partial');return this.i18n.t('pending.kind.operational')}
  priorityLabel(priority:string):string{return this.i18n.t(PENDING_PRIORITY_KEYS[priority]??'pending.priority.normal')}statusLabel(status:string):string{return this.i18n.t(PENDING_STATUS_KEYS[status]??'pending.status.open')}
  isPartial(item:PendingItem):boolean{return pendingIsPartial(item)}isStale(item:PendingItem):boolean{return pendingIsStale(item.updated_at)}hasEvidence(item:PendingItem):boolean{return Object.keys(item.evidence).length>0}evidence(item:PendingItem):string{return JSON.stringify(item.evidence,null,2)}
  failureTitle():string{return this.i18n.t(this.failure()?.kind==='not-found'?'pending.notFoundTitle':this.failure()?.kind==='forbidden'?'pending.forbiddenTitle':this.failure()?.kind==='unavailable'?'pending.unavailableTitle':'pending.errorTitle')}
  failureMessage():string{return this.i18n.t(this.failure()?.kind==='not-found'?'pending.notFound':this.failure()?.kind==='forbidden'?'pending.forbidden':this.failure()?.kind==='unavailable'?'pending.unavailable':'pending.error')}
}
