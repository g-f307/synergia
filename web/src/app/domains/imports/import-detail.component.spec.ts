import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { I18nService } from '../../shared/i18n/i18n.service';
import { ImportDetailComponent } from './import-detail.component';
import { ImportService } from './import.service';

describe('ImportDetailComponent', () => {
  const imports = {
    get: () => of({ execution_id: 'exec-1', status: 'completed_with_errors', source: 'N-FP', file_name: 'plan.csv', started_at: '2026-09-02T12:00:00Z' }),
    inspections: () => of([{ inspection_id: 1, source: 'N-FP', original_file_name: 'plan.csv', size_bytes: 100, decision: 'accepted', reason_code: 'accepted', analyzed_at: '2026-09-02T12:00:00Z', retained_until: null, discarded_at: null }]),
    summary: () => of({ rows_read: 3, valid_records: 2, rejected_records: 1, normalized_records: 2, errors: 1, warnings: 0 })
  };
  beforeEach(async () => {
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
});
