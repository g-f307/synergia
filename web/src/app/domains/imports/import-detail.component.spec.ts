import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { ImportDetailComponent } from './import-detail.component';
import { ImportService } from './import.service';

describe('ImportDetailComponent', () => {
  const imports = { get: jasmine.createSpy('get'), inspections: jasmine.createSpy('inspections'), resultSummary: jasmine.createSpy('resultSummary'), issues: jasmine.createSpy('issues'), issuesCsv: jasmine.createSpy('issuesCsv') };
  beforeEach(async () => {
    imports.get.calls.reset();
    imports.inspections.calls.reset();
    imports.resultSummary.calls.reset();
    imports.get.and.returnValue(of({ execution_id: 'exec-1', status: 'completed_with_errors', source: 'N-FP', file_name: 'plan.csv', started_at: '2026-09-02T12:00:00Z' }));
    imports.inspections.and.returnValue(of([{ inspection_id: 1, source: 'N-FP', original_file_name: 'plan.csv', size_bytes: 100, decision: 'accepted', reason_code: 'accepted', analyzed_at: '2026-09-02T12:00:00Z', retained_until: null, discarded_at: null }]));
    imports.resultSummary.and.returnValue(of({ execution_id: 'exec-1', execution_status: 'completed_with_errors', summary_status: 'ready', summary: { rows_read: 3, valid_records: 2, rejected_records: 1, normalized_records: 2, errors: 1, warnings: 0 }, issues_total: 1, reason_code: 'summary_persisted', generated_at: '2026-11-17T12:00:00Z' }));
    imports.issues.and.returnValue(of({ items: [], pagination: { page: 1, page_size: 20, total: 0, pages: 0 }, sort: 'oldest', generated_at: '2026-11-17T12:00:00Z' }));
    await TestBed.configureTestingModule({
      imports: [ImportDetailComponent],
      providers: [provideRouter([]), { provide: ImportService, useValue: imports }, { provide: ActivatedRoute, useValue: { paramMap: of(convertToParamMap({ executionId: 'exec-1' })), queryParamMap: of(convertToParamMap({})), snapshot: { queryParamMap: convertToParamMap({}) } } }, { provide: SessionService, useValue: { hasPermission: () => true } }]
    }).compileComponents();
  });

  it('shows accepted inspection and pipeline counts in Portuguese', () => {
    const fixture = TestBed.createComponent(ImportDetailComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Concluída com erros');
    expect(fixture.nativeElement.textContent).toContain('Arquivo aceito');
    expect(fixture.nativeElement.textContent).toContain('Registros rejeitados');
    expect(fixture.nativeElement.textContent).not.toContain('/secret');
    const executionLink = fixture.nativeElement.querySelector('[data-testid="related-execution"]') as HTMLAnchorElement;
    expect(executionLink.getAttribute('href')).toContain('/executions/exec-1');
    expect(executionLink.getAttribute('href')).toContain('from=%2Fimports%2Fexec-1');
  });

  it('localizes the result in English', () => {
    TestBed.inject(I18nService).configure('en-US');
    const fixture = TestBed.createComponent(ImportDetailComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Completed with errors');
    expect(fixture.nativeElement.textContent).toContain('File accepted');
  });

  it('shows unavailable and forbidden auxiliary responses as a partial result', () => {
    imports.inspections.and.returnValue(throwError(() => failure('unavailable', 500, 'corr-inspection')));
    imports.resultSummary.and.returnValue(throwError(() => failure('forbidden', 403, 'corr-summary')));
    const fixture = TestBed.createComponent(ImportDetailComponent);
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;
    expect(fixture.componentInstance.inspectionState()).toBe('unavailable');
    expect(fixture.componentInstance.summaryState()).toBe('forbidden');
    expect(text).toContain('Resultado parcial');
    expect(text).toContain('inspeção está temporariamente indisponível');
    expect(text).toContain('não possui permissão para consultar o resumo');
    expect(fixture.nativeElement.querySelector('input[value]')).toBeNull();
    expect([...fixture.nativeElement.querySelectorAll('details input')].map((input) => (input as HTMLInputElement).value)).toContain('corr-inspection');
    expect(fixture.nativeElement.querySelector('details').open).toBeFalse();
    expect(text).not.toContain('Nenhum registro de inspeção');
  });

  it('distinguishes expected missing auxiliary resources from failures', () => {
    imports.inspections.and.returnValue(throwError(() => failure('not-found', 404)));
    imports.resultSummary.and.returnValue(throwError(() => failure('not-found', 404)));
    const fixture = TestBed.createComponent(ImportDetailComponent);
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;
    expect(fixture.componentInstance.inspectionState()).toBe('missing');
    expect(fixture.componentInstance.summaryState()).toBe('missing');
    expect(text).toContain('inspeção não foi encontrada');
    expect(text).toContain('resumo não foi encontrado');
    expect(text).not.toContain('processamento está em andamento');
    expect(text).not.toContain('temporariamente indisponível');
  });

  it('uses one consistent surface with a visible title and internally scrolling content', () => {
    const fixture = TestBed.createComponent(ImportDetailComponent);
    fixture.detectChanges();
    const page = fixture.nativeElement.querySelector('.import-detail') as HTMLElement;
    const body = fixture.nativeElement.querySelector('.detail-scroll') as HTMLElement;
    expect(getComputedStyle(page).overflow).toBe('hidden');
    expect(getComputedStyle(body).overflowY).toBe('auto');
    expect(fixture.nativeElement.querySelector('h1')?.textContent).toContain('Detalhes da importação');
    expect(fixture.nativeElement.querySelectorAll('.card').length).toBe(0);
    expect(fixture.nativeElement.querySelector('.eyebrow')).toBeNull();
    expect(fixture.nativeElement.querySelector('.inspection-icon')).toBeNull();
    expect(fixture.nativeElement.querySelector('.status-icon')).toBeNull();
  });

  function failure(kind: ApiFailure['kind'], status: number, correlationId: string | null = null): ApiFailure {
    return { kind, status, code: 'synthetic_failure', message: 'safe', correlationId, fields: [] };
  }
});
