import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, UrlTree, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject, Subject, of, throwError } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { reportDetail, reportPage, reportPolicy, reportVersion } from './report.fixtures';
import { ReportPage } from './report.models';
import { ReportCatalogComponent } from './report-catalog.component';
import { ReportService } from './report.service';

describe('ReportCatalogComponent', () => {
  let fixture: ComponentFixture<ReportCatalogComponent>; let response: Subject<ReportPage>; let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>; let router: jasmine.SpyObj<Router>; let create: jasmine.Spy; let list: jasmine.Spy; let policy: jasmine.Spy; const granted = signal(['report.read', 'report.generate', 'report.export']);
  beforeEach(async () => {
    granted.set(['report.read', 'report.generate', 'report.export']); response = new Subject(); params = new BehaviorSubject(convertToParamMap({ type: 'oqc_summary', state: 'succeeded', sort: 'oldest', page: '2', pageSize: '10' }));
    router = jasmine.createSpyObj<Router>('Router', ['navigate', 'createUrlTree', 'serializeUrl'], { events: new Subject(), url: '/reports?type=oqc_summary&page=2' }); router.navigate.and.resolveTo(true); router.createUrlTree.and.returnValue({} as UrlTree); router.serializeUrl.and.returnValue('/reports/1');
    create = jasmine.createSpy().and.returnValue(of(reportDetail())); list = jasmine.createSpy().and.returnValue(response.asObservable()); policy = jasmine.createSpy().and.returnValue(of(reportPolicy()));
    await TestBed.configureTestingModule({ imports: [ReportCatalogComponent], providers: [provideRouter([]), { provide: Router, useValue: router }, { provide: ActivatedRoute, useValue: { queryParamMap: params.asObservable() } }, { provide: ReportService, useValue: { policy, list, create, export: () => of({ body: new Blob(['safe']), headers: { get: () => null } }) } }, { provide: SessionService, useValue: { hasPermission: (key: string) => granted().includes(key) } }] }).compileComponents();
    fixture = TestBed.createComponent(ReportCatalogComponent); fixture.detectChanges();
  });
  it('renders empty and partial catalog states without fixed report data', () => { response.next(reportPage([])); fixture.detectChanges(); expect(fixture.nativeElement.querySelector('[data-state="empty"]')).not.toBeNull(); response.next(reportPage([reportVersion({ completeness: 'partial' })])); fixture.detectChanges(); expect(fixture.nativeElement.querySelector('[data-state="partial"]')).not.toBeNull(); expect(fixture.nativeElement.textContent).toContain('exec-1'); });
  it('preserves filters, sorting and pagination in the URL', () => { fixture.componentInstance.organizationId.set('org-1'); fixture.componentInstance.executionId.set('exec-9'); fixture.componentInstance.changePage(3); expect(router.navigate).toHaveBeenCalledWith([], { relativeTo: jasmine.anything(), queryParams: jasmine.objectContaining({ organization: 'org-1', type: 'oqc_summary', state: 'succeeded', execution: 'exec-9', sort: 'oldest', page: 3, pageSize: 10 }) }); });
  it('requires and sends an organization for generation', () => { fixture.componentInstance.generationOrganization.set(''); fixture.componentInstance.generationExecution.set('exec-1'); fixture.componentInstance.generate(new Event('submit')); expect(create).not.toHaveBeenCalled(); fixture.componentInstance.generationOrganization.set('44444444-4444-4444-8444-444444444444'); fixture.componentInstance.generate(new Event('submit')); expect(create).toHaveBeenCalledWith(jasmine.objectContaining({ organization_id: '44444444-4444-4444-8444-444444444444', execution_id: 'exec-1' })); });
  it('defaults the reference after the current minute so recent executions are included', () => {
    const reference = new Date(fixture.componentInstance.referenceAt()).getTime();
    expect(reference).toBeGreaterThanOrEqual(Date.now());
    expect(reference).toBeLessThan(Date.now() + 61_000);
  });
  it('works in English using the same real journey', () => { TestBed.inject(I18nService).configure('en-US'); response.next(reportPage([])); fixture.detectChanges(); expect(fixture.nativeElement.textContent).toContain('No reports found'); });
  it('reloads the current query when refresh is requested', () => { expect(list).toHaveBeenCalledTimes(1); fixture.componentInstance.refresh(); expect(list).toHaveBeenCalledTimes(2); });
  it('hides generation and export actions without their effective permissions', () => { granted.set(['report.read']); response.next(reportPage([reportVersion()])); fixture.detectChanges(); const text = fixture.nativeElement.textContent as string; expect(text).not.toContain('Gerar relatório'); expect(text).not.toContain('Exportar CSV'); expect(text).toContain('Visualizar'); });
  it('represents a forbidden policy distinctly from temporary unavailability', () => {
    fixture.destroy();
    policy.and.returnValue(throwError(() => ({ kind: 'forbidden', status: 403, code: 'access_denied', message: 'safe', correlationId: 'policy-403', fields: [] } as ApiFailure)));
    fixture = TestBed.createComponent(ReportCatalogComponent); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-state="forbidden"]')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Acesso não permitido');
    expect(fixture.nativeElement.textContent).toContain('policy-403');
    expect(fixture.nativeElement.textContent).not.toContain('Opções indisponíveis');
  });
});
