import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject, Subject, of, throwError } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { ImportDetailComponent } from './import-detail.component';
import { ImportIssuePage, ImportResultSummary, ImportStatus } from './import.models';
import { ImportService } from './import.service';

const totals = { rows_read: 3, valid_records: 2, rejected_records: 1, normalized_records: 2, errors: 1, warnings: 0 };
function result(changes: Partial<ImportResultSummary> = {}): ImportResultSummary {
  return { execution_id: 'exec-1', execution_status: 'completed_with_errors', summary_status: 'ready', summary: totals, issues_total: 1, generated_at: '2026-11-17T12:00:00Z', reason_code: 'summary_persisted', inspection_reason_code: null, duplicate_of_execution_id: null, correlationId: 'corr-result', ...changes };
}
function page(changes: Partial<ImportIssuePage> = {}): ImportIssuePage {
  return { items: [{ id: 1, severity: 'error', safe_file_name: 'arquivo-1.csv', sheet_name: 'CSV', row_number: 2, column_name: 'A', code: 'required_field', reason: '/secret must not be rendered', scope: 'record', occurred_at: '2026-11-17T12:00:00Z' }], pagination: { page: 1, page_size: 20, total: 1, pages: 1 }, sort: 'oldest', generated_at: '2026-11-17T12:00:00Z', ...changes };
}
const failure = (kind: ApiFailure['kind'], status: number): ApiFailure => ({ kind, status, code: 'import_issues_unavailable', message: 'Safe', correlationId: 'corr-issues', fields: [] });

describe('Import detail availability, issues and request lifecycle', () => {
  let imports: jasmine.SpyObj<ImportService>;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let query: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let route: { paramMap: typeof params; queryParamMap: typeof query; snapshot: { queryParamMap: ReturnType<typeof convertToParamMap> } };
  beforeEach(async () => {
    imports = jasmine.createSpyObj<ImportService>('ImportService', ['get', 'inspections', 'resultSummary', 'issues', 'issuesCsv', 'summary', 'upload']);
    imports.get.and.returnValue(of({ execution_id: 'exec-1', status: 'completed_with_errors', source: 'N-FP', file_name: 'synthetic.csv', started_at: '2026-11-17T12:00:00Z' } as ImportStatus));
    imports.inspections.and.returnValue(of([]));
    imports.resultSummary.and.returnValue(of(result()));
    imports.issues.and.returnValue(of(page()));
    imports.issuesCsv.and.returnValue(of(new Blob(['id,reason\r\n1,Safe\r\n'], { type: 'text/csv' })));
    params = new BehaviorSubject(convertToParamMap({ executionId: 'exec-1' }));
    query = new BehaviorSubject(convertToParamMap({}));
    route = { paramMap: params, queryParamMap: query, snapshot: { queryParamMap: query.value } };
    await TestBed.configureTestingModule({ imports: [ImportDetailComponent], providers: [provideRouter([]), { provide: ActivatedRoute, useValue: route }, { provide: ImportService, useValue: imports }, { provide: SessionService, useValue: { hasPermission: (key: string) => key === 'import.read' } }] }).compileComponents();
  });
  function create() { const fixture = TestBed.createComponent(ImportDetailComponent); fixture.detectChanges(); return fixture; }
  function setQuery(values: Record<string, string>) { const map = convertToParamMap(values); route.snapshot.queryParamMap = map; query.next(map); }

  for (const [kind, status] of [['unauthorized', 401], ['forbidden', 403], ['not-found', 404]] as const) {
    for (const section of ['resultSummary', 'inspections', 'issues', 'issuesCsv'] as const) {
      it(`clears loaded diagnostics after ${status} from ${section}`, () => {
        const fixture = create();
        expect(fixture.nativeElement.querySelector('.issues-table')).not.toBeNull();
        imports[section].and.returnValue(throwError(() => failure(kind, status)));
        const component = fixture.componentInstance;
        if (section === 'resultSummary') component.loadSummary();
        if (section === 'inspections') component.loadInspections();
        if (section === 'issues') component.loadIssues(true);
        if (section === 'issuesCsv') component.exportCsv();
        fixture.detectChanges();
        expect(component.item()).toBeNull(); expect(component.result()).toBeNull();
        expect(component.inspections()).toEqual([]); expect(component.issuePage()).toBeNull();
        expect(fixture.nativeElement.querySelector('.issues-table')).toBeNull();
        expect(fixture.nativeElement.querySelector('[data-testid="import-counts"]')).toBeNull();
        expect(component.failure()?.status).toBe(status);
      });
    }
  }

  it('cancels every pending section and export before they can repopulate revoked data', () => {
    const fixture = create(); const component = fixture.componentInstance;
    const summary = new Subject<ImportResultSummary>();
    const inspection = new Subject<never[]>(); const issues = new Subject<ImportIssuePage>();
    const download = new Subject<Blob>();
    imports.resultSummary.and.returnValue(summary); imports.inspections.and.returnValue(inspection);
    imports.issuesCsv.and.returnValue(download);
    component.loadSummary(); component.loadInspections(); component.exportCsv();
    imports.issues.and.returnValue(issues); component.loadIssues(true);
    // loadIssues cancels the earlier export. Start one while the page is loaded.
    issues.next(page()); component.exportCsv();
    summary.error(failure('forbidden', 403));
    expect(inspection.observed).toBeFalse(); expect(issues.observed).toBeFalse();
    expect(download.observed).toBeFalse();
    inspection.next([]); issues.next(page()); download.next(new Blob(['stale']));
    component.refreshResult(); setQuery({ page: '2' }); fixture.detectChanges();
    expect(component.item()).toBeNull(); expect(component.issuePage()).toBeNull();
    expect(fixture.nativeElement.querySelector('.issues-table')).toBeNull();
    imports.resultSummary.and.returnValue(of(result())); imports.inspections.and.returnValue(of([]));
    imports.issues.and.returnValue(of(page()));
    component.loadImport(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.issues-table')).not.toBeNull();
  });

  it('requires only import.read and uses public explanations instead of raw reasons', () => {
    const fixture = create();
    expect(fixture.nativeElement.querySelector('.issues-table')).not.toBeNull();
    const label = fixture.nativeElement.querySelector('label[for="import-severity"]') as HTMLLabelElement;
    expect(label.textContent?.trim()).toBe('Severidade');
    expect(label.control?.id).toBe('import-severity');
    expect(fixture.nativeElement.textContent).toContain('Campo obrigatório vazio');
    expect(fixture.nativeElement.textContent).not.toContain('/secret');
    expect(fixture.nativeElement.querySelector('[data-testid="related-execution"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('a[href="/imports/new"]')).toBeNull();
    expect(imports.summary).not.toHaveBeenCalled();
  });

  it('distinguishes persisted zero counts from absent counts and zero issues', () => {
    imports.resultSummary.and.returnValue(of(result({ summary: { rows_read: 0, valid_records: 0, rejected_records: 0, normalized_records: 0, errors: 0, warnings: 0 }, issues_total: 0 })));
    imports.issues.and.returnValue(of(page({ items: [], pagination: { page: 1, page_size: 20, total: 0, pages: 0 } })));
    const fixture = create();
    expect([...fixture.nativeElement.querySelectorAll('[data-testid="import-counts"] dd')].map(node => (node as HTMLElement).textContent)).toEqual(['0', '0', '0', '0', '0', '0']);
    expect(fixture.nativeElement.textContent).toContain('Nenhuma divergência registrada');
    expect(fixture.nativeElement.querySelector('syn-pagination')).toBeNull();
  });

  for (const [reason, expected] of [['summary_unavailable', 'Não há contagens persistidas'], ['preparation_error', 'falhou na preparação']]) {
    it(`shows terminal ${reason} as unavailable without invented zeros`, () => {
      imports.resultSummary.and.returnValue(of(result({ summary_status: 'unavailable', summary: null, reason_code: reason, execution_status: 'failed' })));
      const fixture = create();
      expect(fixture.nativeElement.textContent).toContain(expected);
      expect(fixture.nativeElement.textContent).not.toContain('processamento está em andamento');
      expect(fixture.nativeElement.querySelector('[data-testid="import-counts"]')).toBeNull();
      expect(fixture.nativeElement.querySelector('details input').value).toBe('corr-result');
      expect(fixture.nativeElement.querySelector('details').open).toBeFalse();
    });
  }

  it('refreshes processing using only GETs, without reimporting', () => {
    imports.resultSummary.and.returnValue(of(result({ summary_status: 'processing', summary: null, execution_status: 'validating', reason_code: 'execution_processing' })));
    const fixture = create();
    expect(fixture.nativeElement.textContent).toContain('processamento está em andamento');
    imports.resultSummary.and.returnValue(of(result()));
    fixture.componentInstance.refreshResult(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-testid="import-counts"]')).not.toBeNull();
    expect(imports.issues).toHaveBeenCalledTimes(2); expect(imports.get).toHaveBeenCalledTimes(1);
    expect(imports.upload).not.toHaveBeenCalled();
  });

  for (const previous of [null, 'prior-authorized']) {
    it(`links to a previous import only if returned as authorized (${previous})`, () => {
      imports.resultSummary.and.returnValue(of(result({ summary_status: 'not_applicable', summary: null, reason_code: 'duplicate', execution_status: 'duplicate', duplicate_of_execution_id: previous })));
      const fixture = create();
      expect(fixture.nativeElement.textContent).toContain('Nenhum processamento duplicado');
      expect(fixture.nativeElement.querySelector('.previous-import')?.getAttribute('href') ?? null).toBe(previous ? '/imports/' + previous : null);
    });
  }

  it('explains a macro rejection without processing or showing counts', () => {
    imports.resultSummary.and.returnValue(of(result({ summary_status: 'not_applicable', summary: null, reason_code: 'security_rejected', inspection_reason_code: 'macro_or_active_content' })));
    const fixture = create();
    expect(fixture.nativeElement.textContent).toContain('Macros ou conteúdo ativo');
    expect(fixture.nativeElement.querySelector('[data-testid="import-counts"]')).toBeNull();
  });

  for (const [kind, status] of [['not-found', 404], ['forbidden', 403], ['unauthorized', 401], ['unavailable', 503]] as const) {
    it(`does not mask summary HTTP ${status} as processing`, () => {
      imports.resultSummary.and.returnValue(throwError(() => failure(kind, status)));
      const fixture = create();
      expect(fixture.nativeElement.textContent).not.toContain('processamento está em andamento');
      expect(fixture.nativeElement.querySelector('details input').value).toBe('corr-issues');
      expect(fixture.nativeElement.querySelector('details').open).toBeFalse();
    });
  }

  it('preserves loaded counts after issues fail and retries only that section', () => {
    imports.issues.and.returnValue(throwError(() => failure('unavailable', 503)));
    const fixture = create();
    expect(fixture.nativeElement.querySelector('[data-testid="import-counts"]')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Resultado parcial');
    imports.issues.and.returnValue(of(page())); fixture.componentInstance.loadIssues(true); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.issues-table')).not.toBeNull();
    expect(imports.resultSummary).toHaveBeenCalledTimes(1); expect(imports.inspections).toHaveBeenCalledTimes(1);
  });

  it('shows unknown location explicitly without inventing row or field', () => {
    const data = page(); data.items[0] = { ...data.items[0], row_number: null, column_name: null, sheet_name: null, safe_file_name: null };
    imports.issues.and.returnValue(of(data));
    expect(create().nativeElement.querySelector('tbody').textContent.match(/Não informado/g).length).toBe(4);
  });

  it('restores URL filters and resets pagination on severity change', () => {
    setQuery({ severity: 'warning', page: '3' }); const fixture = create();
    expect(imports.issues).toHaveBeenCalledOnceWith('exec-1', 3, 'warning');
    const navigate = spyOn(TestBed.inject(Router), 'navigate').and.resolveTo(true);
    fixture.componentInstance.filterSeverity('error');
    expect(navigate).toHaveBeenCalledWith([], jasmine.objectContaining({ queryParams: { severity: 'error', page: 1 }, queryParamsHandling: 'merge' }));
    setQuery({ severity: 'error', page: '1' });
    expect(imports.issues).toHaveBeenCalledWith('exec-1', 1, 'error');
    fixture.componentInstance.goToPage(2);
    expect(navigate).toHaveBeenCalledWith([], jasmine.objectContaining({ queryParams: { page: 2 }, queryParamsHandling: 'merge' }));
  });

  it('normalizes malformed filters and keeps navigation for a page past the last', () => {
    setQuery({ severity: 'unsafe', page: 'NaN' });
    imports.issues.and.returnValue(of(page({ items: [], pagination: { page: 4, page_size: 20, total: 55, pages: 3 } })));
    const fixture = create();
    expect(imports.issues).toHaveBeenCalledOnceWith('exec-1', 1, '');
    expect(fixture.nativeElement.textContent).toContain('Esta página não possui ocorrências');
    expect(fixture.nativeElement.querySelectorAll('syn-pagination').length).toBe(1);
  });

  it('cancels stale page and export responses when filters change', () => {
    const oldPage = new Subject<ImportIssuePage>(); const oldExport = new Subject<Blob>();
    imports.issues.and.returnValue(oldPage); const fixture = create(); oldPage.next(page());
    imports.issuesCsv.and.returnValue(oldExport); fixture.componentInstance.exportCsv();
    expect(oldExport.observed).toBeTrue();
    imports.issues.and.returnValue(of(page({ items: [] }))); setQuery({ severity: 'warning' });
    expect(oldPage.observed).toBeFalse(); expect(oldExport.observed).toBeFalse();
    oldPage.next(page()); expect(fixture.componentInstance.issuePage()?.items).toEqual([]);
    expect(fixture.componentInstance.exporting()).toBeFalse();
  });

  it('cancels reads on execution changes and component destruction', () => {
    const oldSummary = new Subject<ImportResultSummary>(); const oldIssues = new Subject<ImportIssuePage>();
    imports.resultSummary.and.returnValue(oldSummary); imports.issues.and.returnValue(oldIssues);
    const fixture = create();
    imports.resultSummary.and.returnValue(of(result({ execution_id: 'exec-2' }))); imports.issues.and.returnValue(of(page()));
    imports.get.and.returnValue(of({ execution_id: 'exec-2', status: 'completed', source: 'N-FP', started_at: '2026-11-17T12:00:00Z' } as ImportStatus));
    params.next(convertToParamMap({ executionId: 'exec-2' }));
    expect(oldSummary.observed).toBeFalse(); expect(oldIssues.observed).toBeFalse();
    oldSummary.next(result()); expect(fixture.componentInstance.result()?.execution_id).toBe('exec-2');
    const pending = new Subject<ImportIssuePage>(); imports.issues.and.returnValue(pending);
    fixture.componentInstance.loadIssues(true); fixture.destroy(); expect(pending.observed).toBeFalse();
  });

  it('downloads the full current filter and releases the temporary object URL', () => {
    spyOn(URL, 'createObjectURL').and.returnValue('blob:synthetic');
    const revoke = spyOn(URL, 'revokeObjectURL'); const click = spyOn(HTMLAnchorElement.prototype, 'click');
    setQuery({ severity: 'warning', page: '2' }); const fixture = create(); fixture.componentInstance.exportCsv();
    expect(imports.issuesCsv).toHaveBeenCalledOnceWith('exec-1', 'warning');
    expect(click).toHaveBeenCalled(); expect(revoke).toHaveBeenCalledWith('blob:synthetic');
    expect(fixture.componentInstance.exporting()).toBeFalse();
  });

  it('preserves loaded table and counts on CSV failure, allowing explicit retry', () => {
    imports.issuesCsv.and.returnValue(throwError(() => failure('unavailable', 503)));
    const fixture = create(); fixture.componentInstance.exportCsv(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-testid="import-counts"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.issues-table')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('exportação está temporariamente indisponível');
    fixture.componentInstance.exportCsv(); expect(imports.issuesCsv).toHaveBeenCalledTimes(2);
  });
});
