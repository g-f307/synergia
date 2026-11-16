import { Component, Input, OnChanges, OnDestroy, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Subscription, switchMap, of } from 'rxjs';

import { AiAssistanceCapability, AiAssistanceCapabilityService } from '../../core/ai-assistance-capability.service';
import { AiAssistanceResponse, AiAssistanceService } from '../../core/ai-assistance.service';
import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { AlertComponent, BadgeComponent } from '../../shared/ui/ui-kit';
import { Execution } from './execution.models';

type AssistanceState = 'hidden' | 'loading' | 'empty' | 'active' | 'generating'
  | AiAssistanceResponse['state'] | 'timeout' | 'conflict' | 'forbidden' | 'expired' | 'error' | 'rateLimited';
const STATE_LABELS: Record<AssistanceState, TranslationKey> = {
  hidden: 'assistance.title',
  loading: 'assistance.state.loading',
  empty: 'assistance.state.empty',
  active: 'assistance.state.active',
  generating: 'assistance.state.generating',
  ready: 'assistance.state.ready',
  insufficient_evidence: 'assistance.state.insufficient_evidence',
  unavailable: 'assistance.state.unavailable',
  rejected: 'assistance.state.rejected',
  timeout: 'assistance.state.timeout',
  conflict: 'assistance.state.conflict',
  forbidden: 'assistance.state.forbidden',
  expired: 'assistance.state.expired',
  error: 'assistance.state.error',
  rateLimited: 'assistance.state.rateLimited',
};
const STATE_MESSAGES: Partial<Record<AssistanceState, TranslationKey>> = {
  loading: 'assistance.message.loading',
  empty: 'assistance.message.empty',
  active: 'assistance.message.active',
  generating: 'assistance.message.generating',
  unavailable: 'assistance.message.unavailable',
  timeout: 'assistance.message.timeout',
  conflict: 'assistance.message.conflict',
  forbidden: 'assistance.message.forbidden',
  expired: 'assistance.message.expired',
  error: 'assistance.message.error',
  rateLimited: 'assistance.message.rateLimited',
};
const TERMINAL = ['completed', 'partial', 'failed'];
export const REFERENCE_TABS = { DIV: 'divergences', PEN: 'pending', CLA: 'classifications', EVI: 'evidences', HIS: 'history' } as const;

@Component({
  selector: 'syn-execution-assistance',
  imports: [RouterLink, AlertComponent, BadgeComponent],
  templateUrl: './execution-assistance.component.html',
  styleUrl: './execution-assistance.component.css',
})
export class ExecutionAssistanceComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) execution!: Execution;
  readonly i18n = inject(I18nService);
  private readonly api = inject(AiAssistanceService);
  private readonly capabilities = inject(AiAssistanceCapabilityService);
  private readonly session = inject(SessionService);
  private requests = new Subscription();
  readonly capability = signal<AiAssistanceCapability | null>(null);
  readonly state = signal<AssistanceState>('hidden');
  readonly result = signal<AiAssistanceResponse | null>(null);
  readonly visible = computed(() => this.state() !== 'hidden');
  readonly busy = computed(() => ['loading', 'generating'].includes(this.state()));
  readonly failed = computed(() => ['timeout', 'conflict', 'forbidden', 'expired', 'error', 'rateLimited', 'unavailable'].includes(this.state()) && !this.result());
  readonly canGenerate = computed(() => !!this.capability()?.generate && !this.result()
    && !['loading', 'active', 'forbidden', 'expired', 'hidden', 'conflict', 'timeout', 'rateLimited'].includes(this.state()));

  ngOnChanges(): void { this.load(); }
  ngOnDestroy(): void { this.requests.unsubscribe(); }

  load(): void {
    this.requests.unsubscribe();
    this.requests = new Subscription();
    this.capability.set(null);
    this.result.set(null);
    this.state.set('hidden');
    // The server still enforces the execution's organization on every operation.
    if (!this.session.hasPermission('execution.read') || !(
      this.session.hasPermission('ai.assistance.read') || this.session.hasPermission('ai.assistance.generate')
    )) return;
    this.requests.add(this.capabilities.load().pipe(switchMap(capability => {
      this.capability.set(capability);
      if (!capability.enabled || (!capability.read && !capability.generate)) return of(null);
      if (!TERMINAL.includes(this.execution.lifecycle ?? '')) {
        this.state.set('active');
        return of(null);
      }
      this.state.set('loading');
      return capability.read ? this.api.latest(this.execution.execution_id) : of(null);
    })).subscribe({
      next: result => {
        const capability = this.capability();
        if (!capability?.enabled || (!capability.read && !capability.generate) || this.state() === 'active') return;
        if (result) this.accept(result);
        else this.state.set('empty');
      },
      error: (failure: ApiFailure) => this.fail(failure, true),
    }));
  }

  generate(): void {
    if (!this.canGenerate() || this.busy()) return;
    this.state.set('generating');
    this.requests.add(this.api.generate(this.execution.execution_id).subscribe({
      next: result => this.accept(result),
      error: (failure: ApiFailure) => this.fail(failure),
    }));
  }

  stateLabel(): string { return this.i18n.t(STATE_LABELS[this.state()]); }
  stateMessage(): string { return this.i18n.t(STATE_MESSAGES[this.state()] ?? 'assistance.notice'); }
  referenceTab(reference: string): string | null {
    if (!/^(DIV|PEN|CLA|EVI|HIS)-[A-Za-z0-9_-]{1,64}$/.test(reference)) return null;
    const prefix = reference.slice(0, 3) as keyof typeof REFERENCE_TABS;
    if (['DIV', 'EVI'].includes(prefix) && !this.session.hasPermission('artifact.read')) return null;
    return REFERENCE_TABS[prefix];
  }

  private accept(result: AiAssistanceResponse): void {
    // Never render a response for another execution, even if navigation raced it.
    if (!this.displayable(result)) {
      this.state.set('error');
      return;
    }
    this.result.set(result);
    this.state.set(result.state);
  }
  private displayable(result: AiAssistanceResponse): boolean {
    const text = (value: unknown, max = 600): value is string => typeof value === 'string' && value.length > 0 && Array.from(value).length <= max;
    const texts = (value: unknown, max: number): boolean => Array.isArray(value) && value.length <= max && value.every(item => text(item));
    return !!result && result.execution_id === this.execution.execution_id
      && result.provenance?.contract_version === '1.0.0'
      && ['model', 'deterministic'].includes(result.provenance.origin)
      && ['ready', 'insufficient_evidence', 'unavailable', 'rejected'].includes(result.state)
      && text(result.summary) && typeof result.created_at === 'string' && Number.isFinite(Date.parse(result.created_at))
      && texts(result.human_checks, 3) && texts(result.limitations, 5)
      && Array.isArray(result.findings) && result.findings.length <= 5
      && result.findings.every(finding => finding && text(finding.title, 120) && text(finding.explanation)
        && Array.isArray(finding.evidence_refs) && finding.evidence_refs.length > 0 && finding.evidence_refs.length <= 10
        && finding.evidence_refs.every(reference => typeof reference === 'string' && /^(DIV|PEN|CLA|EVI|HIS)-[A-Za-z0-9_-]{1,64}$/.test(reference)))
      && (result.state === 'ready' || (result.provenance.origin === 'deterministic' && !result.findings.length && !!result.limitations.length));
  }
  private fail(failure: ApiFailure, reading = false): void {
    if (failure.code === 'ai_assistance_generation_disabled') this.load();
    else if (failure.code === 'ai_assistance_disabled') this.state.set('hidden');
    else if (reading && failure.status === 404 && this.capability()?.enabled) this.state.set('empty');
    else if (failure.status === 401) this.state.set('expired');
    else if (failure.status === 403) this.state.set('forbidden');
    else if (failure.code === 'ai_assistance_execution_not_terminal') this.state.set('active');
    else if (failure.status === 409) this.state.set('conflict');
    else if (failure.status === 429) this.state.set('rateLimited');
    else if (failure.status === 504) this.state.set('timeout');
    else if (failure.status === 503 || failure.status === 0) this.state.set('unavailable');
    else this.state.set('error');
  }
}
