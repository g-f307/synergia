import { signal } from '@angular/core';
import { HttpHeaders, HttpResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, UrlTree, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject, Subject, of, throwError } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { reportDetail, reportPage, reportPolicy, reportVersion } from './report.fixtures';
import { ReportDetailComponent } from './report-detail.component';
import { ReportService } from './report.service';

describe('ReportDetailComponent', () => {
  let fixture: ComponentFixture<ReportDetailComponent>; let router: jasmine.SpyObj<Router>; let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>; let api: jasmine.SpyObj<ReportService>;
  const granted = signal(['report.read', 'report.export', 'report.cancel']);
  beforeEach(async () => {
    granted.set(['report.read', 'report.export', 'report.cancel']);
    params = new BehaviorSubject(convertToParamMap({ version: '1', tab: 'data', page: '1', from: '/reports?state=succeeded&page=2' }));
    router = jasmine.createSpyObj<Router>('Router', ['navigate', 'navigateByUrl', 'createUrlTree', 'serializeUrl'], { events: new Subject(), url: '/reports/id?version=1&tab=data' }); router.navigate.and.resolveTo(true); router.navigateByUrl.and.resolveTo(true); router.createUrlTree.and.returnValue({} as UrlTree); router.serializeUrl.and.returnValue('/related');
    api = jasmine.createSpyObj<ReportService>('ReportService', ['policy', 'get', 'versions', 'export', 'cancel']); api.policy.and.returnValue(of(reportPolicy())); api.get.and.returnValue(of(reportDetail())); api.versions.and.returnValue(of(reportPage([reportVersion()]))); api.export.and.returnValue(of(new HttpResponse({ body: new Blob(['safe']), headers: new HttpHeaders({ 'content-disposition': 'attachment; filename="report.csv"' }) })));
    await TestBed.configureTestingModule({ imports: [ReportDetailComponent], providers: [provideRouter([]), { provide: Router, useValue: router }, { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ reportId: '11111111-1111-4111-8111-111111111111' }), queryParamMap: convertToParamMap({ from: '/reports?state=succeeded&page=2' }) }, queryParamMap: params.asObservable() } }, { provide: ReportService, useValue: api }, { provide: SessionService, useValue: { hasPermission: (key: string) => granted().includes(key) } }] }).compileComponents();
    fixture = TestBed.createComponent(ReportDetailComponent); fixture.detectChanges();
  });
  it('renders exact snapshot values and related scoped navigation', () => { const text = fixture.nativeElement.textContent as string; const links = [...fixture.nativeElement.querySelectorAll('a')] as HTMLAnchorElement[]; expect(text).toContain('WO-001'); expect(text).toContain('LOT-001'); expect(text).toContain('0'); expect(text).toContain('Não informado'); expect(links.some((link) => link.textContent?.includes('WO-001'))).toBeTrue(); expect(links.some((link) => link.textContent?.includes('LOT-001'))).toBeTrue(); });
  it('preserves the exact catalog URL when returning', () => { fixture.componentInstance.back(); expect(router.navigateByUrl).toHaveBeenCalledWith('/reports?state=succeeded&page=2'); });
  it('shows history failures instead of hiding them as empty data', async () => { api.versions.and.returnValue(throwError(() => ({ kind: 'unavailable', status: 500, code: 'failure', message: 'safe', correlationId: 'corr', fields: [] } as ApiFailure))); params.next(convertToParamMap({ version: '1', tab: 'history' })); fixture.detectChanges(); expect(fixture.nativeElement.textContent).toContain('Histórico indisponível'); });
  it('renders OQC pending relationships without interpreting content as HTML', () => { api.get.and.returnValue(of(reportDetail({ report_type: 'oqc_summary', data: { kind: 'oqc_summary', count: 1, distinct_lots: 1, by_reason: { hold: 1 }, by_priority: { high: 1 }, by_organization: { ORG: 1 }, items: [{ workorder_number: 'WO-002', lot_number: 'LOT-002', organization_code: 'ORG', decision_state: 'pending', reason: '<script>unsafe()</script>', pending_item_id: 7, priority: 'high', priority_score: 90, pending_reason: 'Review', pending_status: 'open' }] } }))); params.next(convertToParamMap({ version: '1', tab: 'data' })); fixture.detectChanges(); const links = [...fixture.nativeElement.querySelectorAll('a')] as HTMLAnchorElement[]; expect(fixture.nativeElement.textContent).toContain('<script>unsafe()</script>'); expect(fixture.nativeElement.querySelector('script')).toBeNull(); expect(links.some((link) => link.textContent?.includes('Review'))).toBeTrue(); });
  it('supports arrow-key navigation between accessible tabs', () => { const tablist = fixture.nativeElement.querySelector('[role="tablist"]') as HTMLElement; tablist.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })); expect(router.navigate).toHaveBeenCalledWith([], jasmine.objectContaining({ queryParams: { tab: 'history', page: 1 } })); expect(document.activeElement?.id).toBe('report-tab-history'); });
  it('represents policy failures and withholds export controls', () => { fixture.destroy(); api.policy.and.returnValue(throwError(() => ({ kind: 'unavailable', status: 503, code: 'unavailable', message: 'safe', correlationId: 'policy-correlation', fields: [] } as ApiFailure))); fixture = TestBed.createComponent(ReportDetailComponent); fixture.detectChanges(); expect(fixture.nativeElement.textContent).toContain('Opções indisponíveis'); expect(fixture.componentInstance.canExport()).toBeFalse(); });
  it('represents a forbidden policy distinctly from temporary unavailability', () => {
    fixture.destroy();
    api.policy.and.returnValue(throwError(() => ({ kind: 'forbidden', status: 403, code: 'access_denied', message: 'safe', correlationId: 'policy-403', fields: [] } as ApiFailure)));
    fixture = TestBed.createComponent(ReportDetailComponent); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-state="forbidden"]')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Acesso não permitido');
    expect(fixture.nativeElement.textContent).toContain('policy-403');
    expect(fixture.nativeElement.textContent).not.toContain('Opções indisponíveis');
    expect(fixture.componentInstance.canExport()).toBeFalse();
  });
  it('distinguishes generating, completed, partial, stale and failed reports', () => {
    const cases = [
      { report: reportDetail({ state: 'generating', completed_at: null, data: null, created_at: new Date().toISOString() }), expected: 'Em geração' },
      { report: reportDetail(), expected: 'Gerado' },
      { report: reportDetail({ completeness: 'partial' }), expected: 'Dados parciais — revisão necessária' },
      { report: reportDetail({ state: 'generating', completed_at: null, data: null, created_at: '2020-01-01T00:00:00Z' }), expected: 'Geração possivelmente interrompida' },
      { report: reportDetail({ state: 'failed', completeness: null, data: null, failure_code: 'generation_failed', failure_message: 'internal' }), expected: 'Geração não concluída' }
    ];
    for (const item of cases) { api.get.and.returnValue(of(item.report)); params.next(convertToParamMap({ version: '1', tab: 'summary' })); fixture.detectChanges(); expect(fixture.nativeElement.textContent).toContain(item.expected); }
  });
  it('represents forbidden, not-found and unavailable report responses distinctly', () => {
    const cases: Array<{ failure: ApiFailure; expected: string }> = [
      { failure: { kind: 'forbidden', status: 403, code: 'access_denied', message: 'safe', correlationId: 'corr-403', fields: [] }, expected: 'Acesso não permitido' },
      { failure: { kind: 'not-found', status: 404, code: 'resource_not_found', message: 'safe', correlationId: 'corr-404', fields: [] }, expected: 'Relatório não encontrado' },
      { failure: { kind: 'unavailable', status: 500, code: 'internal_error', message: 'safe', correlationId: 'corr-500', fields: [] }, expected: 'Relatórios temporariamente indisponíveis' }
    ];
    for (const item of cases) { api.get.and.returnValue(throwError(() => item.failure)); params.next(convertToParamMap({ version: '1' })); fixture.detectChanges(); expect(fixture.nativeElement.textContent).toContain(item.expected); expect(fixture.nativeElement.textContent).toContain(item.failure.correlationId); }
  });
  it('downloads an authorized export and exposes a forbidden export as a safe state', () => {
    spyOn(URL, 'createObjectURL').and.returnValue('blob:report'); spyOn(URL, 'revokeObjectURL');
    fixture.componentInstance.export();
    expect(api.export).toHaveBeenCalledWith('11111111-1111-4111-8111-111111111111', 1, 'csv');
    api.export.and.returnValue(throwError(() => ({ kind: 'forbidden', status: 403, code: 'access_denied', message: 'safe', correlationId: 'corr-export', fields: [] } as ApiFailure)));
    fixture.componentInstance.export(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-state="forbidden"]')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('corr-export');
  });
  it('renders the report viewer and semantic tab labels in English', () => { TestBed.inject(I18nService).configure('en-US'); params.next(convertToParamMap({ version: '1', tab: 'summary' })); fixture.detectChanges(); expect(fixture.nativeElement.textContent).toContain('Report viewer'); expect(fixture.nativeElement.textContent).toContain('Version history'); expect(fixture.nativeElement.querySelector('[role="tab"][aria-controls="report-panel-summary"]')).not.toBeNull(); });
});
