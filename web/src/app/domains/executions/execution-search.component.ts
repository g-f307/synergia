import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { I18nService } from '../../shared/i18n/i18n.service';

@Component({ template: `<section class="execution-search" aria-labelledby="execution-search-title"><p class="eyebrow">{{ i18n.t('executions.eyebrow') }}</p><h1 id="execution-search-title">{{ i18n.t('executions.monitorTitle') }}</h1><p>{{ i18n.t('executions.monitorHelp') }}</p><form class="card" (submit)="locate($event)"><label for="execution-id">{{ i18n.t('executions.id') }}</label><input id="execution-id" [value]="id()" (input)="id.set($any($event.target).value)" autocomplete="off"><button [disabled]="!id().trim()">{{ i18n.t('executions.locate') }}</button></form></section>`, styles: ['.execution-search{display:grid;gap:var(--space-4);max-width:48rem}form{display:grid;gap:var(--space-3)}'] })
export class ExecutionSearchComponent {
  readonly i18n = inject(I18nService); private readonly router = inject(Router); readonly id = signal('');
  locate(event: Event): void { event.preventDefault(); const id = this.id().trim(); if (id) void this.router.navigate(['/executions', id]); }
}
