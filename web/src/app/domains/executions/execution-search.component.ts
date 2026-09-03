import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { I18nService } from '../../shared/i18n/i18n.service';

@Component({ template: `<section class="execution-search" aria-labelledby="execution-search-title"><header class="page-header"><div><p class="eyebrow">{{ i18n.t('executions.eyebrow') }}</p><h1 id="execution-search-title">{{ i18n.t('executions.monitorTitle') }}</h1><p class="page-subtitle">{{ i18n.t('executions.monitorHelp') }}</p></div></header><form class="card execution-locator" (submit)="locate($event)"><span class="locator-icon" aria-hidden="true">⌕</span><div><label for="execution-id">{{ i18n.t('executions.id') }}</label><input id="execution-id" [value]="id()" (input)="id.set($any($event.target).value)" autocomplete="off"></div><button [disabled]="!id().trim()">{{ i18n.t('executions.locate') }}</button></form></section>`, styles: ['.execution-search{display:grid;gap:var(--space-5);max-width:60rem}.page-header{border-bottom:1px solid var(--syn-border);padding-bottom:var(--syn-space-4)}.execution-locator{align-items:end;display:grid;gap:var(--syn-space-4);grid-template-columns:auto minmax(16rem,1fr) auto}.locator-icon{color:var(--syn-primary);font-size:2rem}@media(max-width:767px){.execution-locator{align-items:stretch;grid-template-columns:1fr}.locator-icon{display:none}}'] })
export class ExecutionSearchComponent {
  readonly i18n = inject(I18nService); private readonly router = inject(Router); readonly id = signal('');
  locate(event: Event): void { event.preventDefault(); const id = this.id().trim(); if (id) void this.router.navigate(['/executions', id], { queryParamsHandling: 'preserve' }); }
}
