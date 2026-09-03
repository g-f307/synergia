import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { ImportDetailComponent } from './import-detail.component';
import { ImportService } from './import.service';

describe('ImportDetailComponent', () => {
  const imports = { get: jasmine.createSpy('get'), inspections: jasmine.createSpy('inspections'), summary: jasmine.createSpy('summary') };
  beforeEach(async () => {
    imports.get.calls.reset();
    imports.inspections.calls.reset();
    imports.summary.calls.reset();
    imports.get.and.returnValue(of({ execution_id: 'exec-1', status: 'completed_with_errors', source: 'N-FP', file_name: 'plan.csv', started_at: '2026-09-02T12:00:00Z' }));
    imports.inspections.and.returnValue(of([{ inspection_id: 1, source: 'N-FP', original_file_name: 'plan.csv', size_bytes: 100, decision: 'accepted', reason_code: 'accepted', analyzed_at: '2026-09-02T12:00:00Z', retained_until: null, discarded_at: null }]));
    imports.summary.and.returnValue(of({ rows_read: 3, valid_records: 2, rejected_records: 1, normalized_records: 2, errors: 1, warnings: 0 }));
    await TestBed.configureTestingModule({
      imports: [ImportDetailComponent],
      providers: [provideRouter([]), { provide: ImportService, useValue: imports }, { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => 'exec-1' } } } }]
    }).compileComponents();
  });

  it('shows accepted inspection and pipeline counts in Portuguese', () => {
    const fixture = TestBed.createComponent(ImportDetailComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Concluída com erros');
    expect(fixture.nativeElement.textContent).toContain('Arquivo aceito');
    expect(fixture.nativeElement.textContent).toContain('Registros rejeitados');
    expect(fixture.nativeElement.textContent).not.toContain('/secret');
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
    imports.summary.and.returnValue(throwError(() => failure('forbidden', 403, 'corr-summary')));
    const fixture = TestBed.createComponent(ImportDetailComponent);
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;
    expect(fixture.componentInstance.inspectionState()).toBe('unavailable');
    expect(fixture.componentInstance.summaryState()).toBe('forbidden');
    expect(text).toContain('Resultado parcial');
    expect(text).toContain('inspeção está temporariamente indisponível');
    expect(text).toContain('não possui permissão para consultar o resumo');
    expect(text).toContain('corr-inspection');
    expect(text).not.toContain('Nenhum registro de inspeção');
  });

  it('distinguishes expected missing auxiliary resources from failures', () => {
    imports.inspections.and.returnValue(throwError(() => failure('not-found', 404)));
    imports.summary.and.returnValue(throwError(() => failure('not-found', 404)));
    const fixture = TestBed.createComponent(ImportDetailComponent);
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;
    expect(fixture.componentInstance.inspectionState()).toBe('missing');
    expect(fixture.componentInstance.summaryState()).toBe('missing');
    expect(text).toContain('inspeção ainda não está disponível');
    expect(text).toContain('resumo ainda não está disponível');
    expect(text).not.toContain('temporariamente indisponível');
  });

  function failure(kind: ApiFailure['kind'], status: number, correlationId: string | null = null): ApiFailure {
    return { kind, status, code: 'synthetic_failure', message: 'safe', correlationId, fields: [] };
  }
});
