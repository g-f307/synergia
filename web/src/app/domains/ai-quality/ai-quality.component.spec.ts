import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';

import { I18nService } from '../../shared/i18n/i18n.service';
import { AiQualityComponent } from './ai-quality.component';
import { AiQualityService, QualityCatalog, QualityExplanation, QualityGroup, QualityModelStatus, QualityResponse } from './ai-quality.service';

describe('AiQualityComponent', () => {
  let fixture: ComponentFixture<AiQualityComponent>;
  let catalog: Subject<QualityCatalog>;
  let generation: Subject<QualityResponse>;
  let generate: jasmine.Spy;
  beforeEach(async () => {
    catalog = new Subject(); generation = new Subject();
    generate = jasmine.createSpy('generate').and.callFake(() => generation.asObservable());
    await TestBed.configureTestingModule({ imports: [AiQualityComponent], providers: [
      { provide: AiQualityService, useValue: { catalog: () => catalog.asObservable(), generate } }
    ] }).compileComponents();
    fixture = TestBed.createComponent(AiQualityComponent); fixture.detectChanges();
  });
  function load(modelStatus: QualityModelStatus = 'available'): void {
    catalog.next({ schema_version: '1.0.0', model_status: modelStatus, scenarios: [
      { id: 'QE-A02', groups: [group()], baseline: [text()] },
      { id: 'QE-A01', groups: [group()], baseline: [text()] },
      { id: 'QD3-E01', groups: [], baseline: [] }
    ] }); fixture.detectChanges();
  }
  it('loads pipeline facts before generation and uses the shared states and frame', () => {
    expect(fixture.nativeElement.querySelector('syn-state')).not.toBeNull(); load();
    expect(fixture.nativeElement.querySelectorAll('tbody tr').length).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('Fatos do pipeline');
    expect(fixture.nativeElement.textContent).toContain('Gere a explicação');
    expect(getComputedStyle(fixture.nativeElement.querySelector('.quality-page')).borderRadius).toBe('28px');
    expect(generate).not.toHaveBeenCalled();
  });
  it('calls the API on demand and prevents duplicate generation while pending', async () => {
    load(); fixture.componentInstance.generate(); fixture.componentInstance.generate(); fixture.detectChanges();
    expect(generate).toHaveBeenCalledOnceWith('QE-A02');
    await fixture.whenStable(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('select').disabled).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Gerando explicação');
    generation.next(response()); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Texto redigido pelo modelo');
    expect(fixture.nativeElement.textContent).toContain('Explicação aceita');
    expect(fixture.nativeElement.querySelectorAll('tbody tr').length).toBe(2);
  });
  it('shows genuine fallback origin and reason without presenting it as AI text', () => {
    load(); fixture.componentInstance.generate();
    generation.next(response({ origin: 'deterministic', state: 'fallback_deterministic', rejection_code: 'runtime_timeout' }));
    fixture.detectChanges();
    const content = fixture.nativeElement.textContent;
    expect(content).toContain('Fallback determinístico'); expect(content).toContain('Texto determinístico');
    expect(content).toContain('excedeu o tempo'); expect(content).not.toContain('Texto redigido pelo modelo');
  });
  it('displays insufficient evidence distinctly and clears an old result when the scenario changes', () => {
    load(); fixture.componentInstance.generate();
    generation.next(response({ state: 'insufficient_evidence' })); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Evidência insuficiente');
    fixture.componentInstance.select('QE-A01'); fixture.detectChanges();
    expect(fixture.componentInstance.response()).toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('Evidência insuficiente');
  });
  it('does not call the model for a clean scenario', () => {
    load(); fixture.componentInstance.select('QD3-E01'); fixture.componentInstance.generate(); fixture.detectChanges();
    expect(generate).not.toHaveBeenCalled(); expect(fixture.nativeElement.textContent).toContain('O modelo não será chamado');
  });
  it('handles denied catalog access without fabricating facts', () => {
    catalog.error({ status: 403 }); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-state="forbidden"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('table')).toBeNull();
  });
  for (const status of ['disabled', 'unavailable'] as const) {
    it(`disables generation when the model is ${status} and keeps the baseline visible`, () => {
      load(status); fixture.componentInstance.generate(); fixture.detectChanges();
      expect(generate).not.toHaveBeenCalled();
      expect(fixture.nativeElement.querySelector('.quality-controls button').disabled).toBeTrue();
      expect(fixture.nativeElement.textContent).toContain(status === 'disabled' ? 'Geração por modelo desabilitada' : 'Modelo validado indisponível');
      expect(fixture.nativeElement.querySelector('details').textContent).toContain(text().explanation);
      fixture.componentInstance.load(); load('available');
      expect(fixture.nativeElement.querySelector('.quality-controls button').disabled).toBeFalse();
    });
  }
  it('keeps the generation HTTP error visible instead of labeling it an accepted response', () => {
    load(); fixture.componentInstance.generate(); generation.error({ status: 500 }); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Não foi possível obter a explicação');
    expect(fixture.componentInstance.response()).toBeNull();
  });
  it('explains a quota denial without displaying an accepted explanation', () => {
    load(); fixture.componentInstance.generate(); generation.error({ status: 429 }); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('limite temporário de geração');
    expect(fixture.componentInstance.response()).toBeNull();
    expect(fixture.componentInstance.generating()).toBeFalse();
  });
  it('translates the interface while explicitly identifying the model language', () => {
    TestBed.inject(I18nService).configure('en-US'); load();
    expect(fixture.nativeElement.textContent).toContain('Generate explanation');
    expect(fixture.nativeElement.textContent).toContain('in Portuguese');
    expect(fixture.nativeElement.querySelector('label').getAttribute('for')).toBe('quality-scenario');
  });
});

function text() { return { explanation: 'A causa não pode ser determinada pelas evidências disponíveis.', human_checks: ['Conferir os campos.'] }; }
function group(): QualityGroup {
  return { code: 'duplicate_serial', category: 'consistency', causal_evidence: 'not_provided', occurrences: [1, 2].map(i => ({
    evidence_id: `ev-${i}`, severity: i === 1 ? 'error' : 'warning', reason: 'Serial duplicado',
    field: { state: 'known', value: 'serial_number' }, column: { state: 'known', value: 'B' },
    row: { state: 'known', value: i + 2 }, sheet: { state: 'known', value: 'synthetic' },
    known_value: { state: 'unavailable' }, unknown_value: { state: 'missing' }
  })) };
}
function response(change: Partial<QualityExplanation> = {}): QualityResponse {
  return { scenario_id: 'QE-A02', mode: 'model', model: 'qwen3:4b-instruct', groups: [{
    group: group(), text: text(), origin: 'model', state: 'accepted_explanation', rejection_code: null,
    response_sha256: 'sha', elapsed_ms: 1000, ...change
  }] };
}
