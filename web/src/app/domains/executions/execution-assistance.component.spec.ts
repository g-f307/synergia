import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject, of, throwError } from 'rxjs';
import { AiAssistanceCapabilityService } from '../../core/ai-assistance-capability.service';
import { AiAssistanceResponse, AiAssistanceService } from '../../core/ai-assistance.service';
import { SessionService } from '../../core/session.service';
import { I18nService } from '../../shared/i18n/i18n.service';
import { ExecutionAssistanceComponent } from './execution-assistance.component';
import { Execution } from './execution.models';

const execution = { execution_id: '00000000-0000-4000-8000-000000000001', lifecycle: 'completed' } as Execution;
export function assistanceFixture(): AiAssistanceResponse {
  return {
    assistance_id: '00000000-0000-4000-8000-000000000002', execution_id: execution.execution_id,
    state: 'ready', summary: 'Fatos disponíveis para conferência.',
    findings: [{ title: 'Registros disponíveis', explanation: 'Há registros para conferência.', evidence_refs: ['DIV-example', 'PEN-example', 'CLA-example', 'EVI-example', 'HIS-example'] }],
    human_checks: ['Conferência humana das evidências.'], limitations: ['A conferência humana é necessária.'],
    provenance: { contract_version: '1.0.0', model: 'internal-model', digest: 'sha256:' + '1'.repeat(64), context_hash: '2'.repeat(64), prompt_hash: '3'.repeat(64), origin: 'model', timings: { context_ms: 0, generation_ms: 0, total_ms: 0 } },
    created_at: '2026-11-15T00:00:00Z',
  };
}
function failure(status: number, code = 'synthetic') {
  return { status, code, kind: 'internal', message: 'internal-secret-never-render', fields: [], correlationId: null };
}

describe('ExecutionAssistanceComponent', () => {
  let fixture: ComponentFixture<ExecutionAssistanceComponent>;
  let component: ExecutionAssistanceComponent;
  let permissions: string[];
  const capability = { load: jasmine.createSpy() };
  const api = { latest: jasmine.createSpy(), generate: jasmine.createSpy() };
  beforeEach(async () => {
    permissions = ['execution.read', 'ai.assistance.read', 'ai.assistance.generate', 'artifact.read'];
    capability.load.calls.reset(); api.latest.calls.reset(); api.generate.calls.reset();
    capability.load.and.returnValue(of({ enabled: true, read: true, generate: true }));
    api.latest.and.returnValue(throwError(() => failure(404)));
    api.generate.and.returnValue(of(assistanceFixture()));
    await TestBed.configureTestingModule({ imports: [ExecutionAssistanceComponent], providers: [
      provideRouter([]), { provide: AiAssistanceCapabilityService, useValue: capability },
      { provide: AiAssistanceService, useValue: api },
      { provide: SessionService, useValue: { hasPermission: (key: string) => permissions.includes(key) } },
    ] }).compileComponents();
    fixture = TestBed.createComponent(ExecutionAssistanceComponent); component = fixture.componentInstance;
  });
  function render(value = execution) { fixture.componentRef.setInput('execution', value); fixture.detectChanges(); }
  function text(): string { return fixture.nativeElement.textContent; }

  it('reads the latest result without automatic generation', () => {
    render(); expect(api.latest).toHaveBeenCalledOnceWith(execution.execution_id);
    expect(api.generate).not.toHaveBeenCalled(); expect(text()).toContain('Sem análise disponível');
    expect(fixture.nativeElement.querySelector('input,textarea,select')).toBeNull();
  });
  for (const allowed of [[], ['execution.read'], ['ai.assistance.read'], ['ai.assistance.generate']]) {
    it(`does not create a card or make requests without both execution and assistance permissions: ${allowed}`, () => {
      permissions = allowed; render(); expect(fixture.nativeElement.querySelector('section')).toBeNull();
      expect(capability.load).not.toHaveBeenCalled(); expect(api.latest).not.toHaveBeenCalled();
    });
  }
  for (const cap of [{ enabled: false, read: false, generate: false }, { enabled: true, read: false, generate: false }]) {
    it(`hides the card for server capability ${JSON.stringify(cap)}`, () => {
      capability.load.and.returnValue(of(cap)); render();
      expect(fixture.nativeElement.querySelector('section')).toBeNull(); expect(api.latest).not.toHaveBeenCalled();
    });
  }
  it('shows an existing analysis to read-only users without a generate action', () => {
    permissions = ['execution.read', 'ai.assistance.read', 'artifact.read'];
    capability.load.and.returnValue(of({ enabled: true, read: true, generate: false }));
    api.latest.and.returnValue(of(assistanceFixture())); render();
    expect(text()).toContain('Análise pronta'); expect(text()).toContain('Fatos disponíveis');
    expect(fixture.nativeElement.querySelector('button')).toBeNull();
    component.generate(); expect(api.generate).not.toHaveBeenCalled();
  });
  it('allows generation without attempting the read endpoint for generate-only capability', () => {
    permissions = ['execution.read', 'ai.assistance.generate'];
    capability.load.and.returnValue(of({ enabled: true, read: false, generate: true })); render();
    expect(api.latest).not.toHaveBeenCalled(); component.generate(); expect(api.generate).toHaveBeenCalledTimes(1);
  });
  it('refreshes capability after generation is suspended and keeps the persisted result visible', () => {
    render();
    capability.load.and.returnValue(of({ enabled: true, read: true, generate: false }));
    api.latest.and.returnValue(of(assistanceFixture()));
    api.generate.and.returnValue(throwError(() => failure(503, 'ai_assistance_generation_disabled')));
    component.generate(); fixture.detectChanges();
    expect(component.visible()).toBeTrue(); expect(component.result()).toEqual(assistanceFixture());
    expect(component.canGenerate()).toBeFalse(); expect(text()).toContain('Fatos disponíveis');
    expect(capability.load).toHaveBeenCalledTimes(2);
    component.generate(); expect(api.generate).toHaveBeenCalledTimes(1);
  });
  it('does not offer forced regeneration when a result exists', () => {
    api.latest.and.returnValue(of(assistanceFixture())); render(); component.generate();
    expect(api.generate).not.toHaveBeenCalled(); expect(fixture.nativeElement.querySelector('button')).toBeNull();
  });
  for (const lifecycle of ['active', null] as const) {
    it(`does not read or generate for non-terminal lifecycle ${lifecycle}`, () => {
      render({ ...execution, lifecycle }); expect(text()).toContain('Execução em andamento');
      expect(api.latest).not.toHaveBeenCalled(); component.generate(); expect(api.generate).not.toHaveBeenCalled();
    });
  }
  for (const lifecycle of ['completed', 'partial', 'failed'] as const) {
    it(`allows explicit generation for terminal lifecycle ${lifecycle}`, () => {
      render({ ...execution, lifecycle }); component.generate(); expect(api.generate).toHaveBeenCalledTimes(1);
    });
  }
  it('announces loading in a small live region', () => {
    api.latest.and.returnValue(new Subject()); render();
    expect(text()).toContain('Carregando análise'); expect(component.busy()).toBeTrue();
    expect(fixture.nativeElement.querySelector('[aria-live="polite"]')?.textContent).toContain('Carregando análise');
    expect(fixture.nativeElement.querySelector('section[aria-live]')).toBeNull();
  });
  it('disables generation, blocks double clicks and then presents the result', () => {
    const response = new Subject<AiAssistanceResponse>(); api.generate.and.returnValue(response); render();
    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    button.click(); fixture.detectChanges(); button.click(); component.generate();
    expect(button.disabled).toBeTrue(); expect(text()).toContain('Gerando análise...'); expect(api.generate).toHaveBeenCalledTimes(1);
    response.next(assistanceFixture()); fixture.detectChanges(); expect(text()).toContain('Análise pronta');
  });
  for (const state of ['ready', 'insufficient_evidence', 'rejected', 'unavailable'] as const) {
    it(`renders the contract state ${state} with origin, timestamp, human checks and limitations`, () => {
      const result = assistanceFixture(); result.state = state;
      if (state !== 'ready') { result.findings = []; result.provenance.origin = 'deterministic'; }
      api.latest.and.returnValue(of(result)); render();
      expect(component.state()).toBe(state); expect(text()).toContain(result.summary);
      expect(text()).toContain(result.limitations[0]); expect(text()).toContain(result.human_checks[0]);
      expect(text()).toContain(state === 'ready' ? 'Gerado por IA' : 'Resumo determinístico');
      expect(fixture.nativeElement.querySelector('time').getAttribute('datetime')).toBe(result.created_at);
    });
  }
  for (const [status, state] of [[403, 'forbidden'], [409, 'conflict'], [429, 'rateLimited'], [503, 'unavailable'], [504, 'timeout'], [401, 'expired'], [500, 'error'], [422, 'error'], [0, 'unavailable']] as const) {
    it(`isolates HTTP ${status} as ${state} without rendering technical errors`, () => {
      render(); api.generate.and.returnValue(throwError(() => failure(status))); component.generate(); fixture.detectChanges();
      expect(component.state()).toBe(state); expect(text()).not.toContain('internal-secret');
      expect(fixture.nativeElement.querySelector('syn-alert')).not.toBeNull();
      if (status === 401) expect(fixture.nativeElement.querySelector('a[href^="/login"]')).not.toBeNull();
    });
  }
  for (const status of [409, 429, 504]) {
    it(`requires a new result check before retrying generation after HTTP ${status}`, () => {
      render(); api.generate.and.returnValue(throwError(() => failure(status)));
      component.generate(); component.generate(); expect(api.generate).toHaveBeenCalledTimes(1);
      component.load(); expect(component.state()).toBe('empty');
      expect(api.latest).toHaveBeenCalledTimes(2); expect(component.canGenerate()).toBeTrue();
    });
  }
  it('rejects another contract version without rendering it', () => {
    const response = assistanceFixture(); Object.assign(response.provenance, { contract_version: '2.0.0' });
    api.latest.and.returnValue(of(response)); render(); expect(component.state()).toBe('error'); expect(component.result()).toBeNull();
  });
  for (const invalid of [
    { state: 'unknown' }, { summary: null }, { created_at: 'invalid date' }, { findings: null },
    { human_checks: Array(4).fill('Overflow') }, { limitations: Array(6).fill('Overflow') },
    { findings: Array(6).fill(assistanceFixture().findings[0]) }, { summary: 'x'.repeat(601) },
  ]) {
    it(`handles invalid display data as an isolated error: ${JSON.stringify(invalid).slice(0, 60)}`, () => {
      api.latest.and.returnValue(of({ ...assistanceFixture(), ...invalid })); render();
      expect(component.state()).toBe('error'); expect(component.result()).toBeNull();
      expect(fixture.nativeElement.querySelector('syn-alert')).not.toBeNull();
    });
  }
  it('uses the non-terminal conflict code to disable generation', () => {
    render(); api.generate.and.returnValue(throwError(() => failure(409, 'ai_assistance_execution_not_terminal')));
    component.generate(); expect(component.state()).toBe('active'); expect(component.canGenerate()).toBeFalse();
  });
  it('hides the card if the server disables assistance while the page is open', () => {
    render(); api.generate.and.returnValue(throwError(() => failure(503, 'ai_assistance_disabled')));
    component.generate(); fixture.detectChanges(); expect(fixture.nativeElement.querySelector('section')).toBeNull();
  });
  it('represents a capability failure without requesting result or generation', () => {
    capability.load.and.returnValue(throwError(() => failure(503))); render();
    expect(component.state()).toBe('unavailable'); expect(api.latest).not.toHaveBeenCalled(); expect(component.canGenerate()).toBeFalse();
  });
  it('checks the existing result again without triggering inference', () => {
    api.latest.and.returnValue(throwError(() => failure(504))); render();
    (fixture.nativeElement.querySelector('button.secondary') as HTMLButtonElement).click();
    expect(api.latest).toHaveBeenCalledTimes(2); expect(api.generate).not.toHaveBeenCalled();
  });
  it('builds keyboard-accessible links for all five reference prefixes, resetting page and preserving query context', () => {
    api.latest.and.returnValue(of(assistanceFixture())); render();
    const anchors = [...fixture.nativeElement.querySelectorAll('.references a')] as HTMLAnchorElement[];
    expect(anchors.length).toBe(5);
    for (const [index, tab] of ['divergences', 'pending', 'classifications', 'evidences', 'history'].entries()) {
      expect(anchors[index].getAttribute('href')).toContain(`tab=${tab}`);
      expect(anchors[index].getAttribute('href')).toContain('page=1');
      expect(anchors[index].getAttribute('href')).toContain('reference=');
    }
    expect(component.referenceTab('javascript:bad')).toBeNull();
  });
  it('does not create links to artifact tabs without permission', () => {
    permissions = ['execution.read', 'ai.assistance.read']; api.latest.and.returnValue(of(assistanceFixture())); render();
    expect(fixture.nativeElement.querySelectorAll('.references a').length).toBe(3); expect(text()).toContain('Acesso à aba restrito');
  });
  it('renders untrusted content as text and does not expose provenance internals', () => {
    const response = assistanceFixture(); response.summary = '<img src=x onerror=alert(1)>';
    response.findings[0].title = '<script>injected</script>'; response.limitations = ['<b>literal</b>'];
    api.latest.and.returnValue(of(response)); render();
    expect(text()).toContain(response.summary); expect(text()).toContain('<b>literal</b>');
    expect(fixture.nativeElement.querySelector('img,script,b')).toBeNull();
    expect(text()).not.toContain(response.provenance.model!); expect(text()).not.toContain(response.provenance.context_hash);
    expect(text()).not.toContain(response.provenance.prompt_hash); expect(text()).not.toContain(response.provenance.digest!);
  });
  it('uses English translations for state, notice, limitations title and actions', () => {
    TestBed.inject(I18nService).configure('en-US'); render();
    expect(text()).toContain('AI-assisted analysis'); expect(text()).toContain('Generate assisted analysis');
    expect(text()).not.toContain('undefined');
  });
  for (const operation of ['latest', 'generate'] as const) {
    it(`cancels ${operation} on destroy and prevents late state updates`, () => {
      const pending = new Subject<AiAssistanceResponse>(); api[operation].and.returnValue(pending); render();
      if (operation === 'generate') component.generate();
      const before = component.state(); fixture.destroy(); expect(pending.observed).toBeFalse();
      pending.next(assistanceFixture()); expect(component.state()).toBe(before);
    });
    it(`cancels ${operation} when execution input changes`, () => {
      const pending = new Subject<AiAssistanceResponse>(); api[operation].and.returnValue(pending); render();
      if (operation === 'generate') component.generate();
      api.latest.and.returnValue(throwError(() => failure(404)));
      render({ ...execution, execution_id: '00000000-0000-4000-8000-000000000003' });
      expect(pending.observed).toBeFalse(); pending.next(assistanceFixture()); expect(component.result()).toBeNull();
    });
  }
  it('cancels capability discovery on destroy', () => {
    const pending = new Subject(); capability.load.and.returnValue(pending); render(); fixture.destroy(); expect(pending.observed).toBeFalse();
  });
  it('rejects results for another execution or contract version', () => {
    api.latest.and.returnValue(of({ ...assistanceFixture(), execution_id: 'foreign' })); render();
    expect(component.state()).toBe('error'); expect(component.result()).toBeNull();
  });
});
