import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject, Subject } from 'rxjs';
import { IndicatorRelatedPage } from '../../shared/api/operational.models';
import { DashboardRelatedComponent } from './dashboard-related.component';
import { DashboardService } from './dashboard.service';

describe('DashboardRelatedComponent', () => {
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let response: Subject<IndicatorRelatedPage>;
  let api: jasmine.SpyObj<DashboardService>;
  beforeEach(async () => {
    params = new BehaviorSubject(convertToParamMap({ organization: 'org-1', dateFrom: '2026-08-01', dateTo: '2026-08-31' }));
    response = new Subject<IndicatorRelatedPage>();
    api = jasmine.createSpyObj<DashboardService>('DashboardService', ['getRelated']);
    api.getRelated.and.callFake(() => response.asObservable());
    await TestBed.configureTestingModule({
      imports: [DashboardRelatedComponent],
      providers: [provideRouter([]),
        { provide: ActivatedRoute, useValue: { queryParamMap: params.asObservable() } },
        { provide: DashboardService, useValue: api }
      ]
    }).compileComponents();
  });

  it('uses current selection, scope and period from the card URL and pins each link', () => {
    const sourceUrl = '/dashboard/related/workorders?organization=org-1&dateFrom=2026-08-01&view=current&page=1';
    spyOnProperty(TestBed.inject(Router), 'url', 'get').and.returnValue(sourceUrl);
    const fixture = TestBed.createComponent(DashboardRelatedComponent);
    fixture.detectChanges(); response.next(page()); fixture.detectChanges();
    expect(api.getRelated).toHaveBeenCalledWith('workorders', jasmine.objectContaining({ organizationId: 'org-1', dateFrom: '2026-08-01T04:00:00Z', dateTo: '2026-09-01T03:59:59.999999Z', page: 1, view: 'current' }));
    expect(fixture.nativeElement.textContent).toContain('Workorders atuais');
    expect(fixture.nativeElement.textContent).toContain('Organizações no escopo dos detalhes: 1');
    expect(fixture.nativeElement.textContent).toContain('01/08/2026');
    const row = fixture.nativeElement.querySelector('.workorder-row') as HTMLAnchorElement;
    expect(row.getAttribute('href')).toContain('/workorders/WO-1');
    const target = new URL(row.href);
    expect(target.searchParams.get('execution_id')).toBe('execution-old');
    expect(target.searchParams.get('organization_id')).toBe('org-1');
    expect(target.searchParams.get('from')).toBe(sourceUrl);
    expect(row.querySelector('.status-pill')?.textContent).toContain('Consolidada');
    expect(row.querySelector('.row-chevron')).not.toBeNull();
  });

  it('restores pagination from the URL and preserves the shared screen frame', () => {
    params.next(convertToParamMap({ page: '2', view: 'current' }));
    const fixture = TestBed.createComponent(DashboardRelatedComponent);
    fixture.detectChanges(); response.next({ ...page(), pagination: { page: 2, pages: 3, total: 51 } }); fixture.detectChanges();
    expect(api.getRelated).toHaveBeenCalledWith('workorders', jasmine.objectContaining({ page: 2, view: 'current' }));
    expect(fixture.nativeElement.textContent).toContain('51');
    expect(fixture.nativeElement.querySelector('syn-pagination')).not.toBeNull();
    expect(getComputedStyle(fixture.nativeElement.querySelector('.workorders-page')).overflow).toBe('hidden');
    expect(getComputedStyle(fixture.nativeElement.querySelector('.workorders-body')).overflowY).toBe('auto');
    const heading = fixture.nativeElement.querySelector('.results-heading') as HTMLElement;
    expect(heading.firstElementChild?.classList).toContain('back-link');
    expect(getComputedStyle(heading).display).toBe('grid');
    expect(getComputedStyle(heading).justifyItems).toBe('start');
    expect(getComputedStyle(fixture.nativeElement.querySelector('.workorder-list')).overflow).toBe('visible');
  });

  it('cancels previous pages and clears protected metadata when authorization is lost', () => {
    const fixture = TestBed.createComponent(DashboardRelatedComponent);
    fixture.detectChanges(); response.next(page()); fixture.detectChanges();
    const old = response; response = new Subject<IndicatorRelatedPage>();
    params.next(convertToParamMap({ page: '2', view: 'current' })); fixture.detectChanges();
    expect(old.observers.length).toBe(0);
    expect(fixture.componentInstance.items()).toEqual([]);
    expect(fixture.componentInstance.scope()).toBeNull();
    expect(fixture.componentInstance.total()).toBe(0);
    old.next(page());
    response.error({kind:'forbidden',status:403}); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.workorder-row')).toBeNull();
    expect(fixture.componentInstance.scope()).toBeNull();
    expect(fixture.nativeElement.querySelector('[data-state="forbidden"]')).not.toBeNull();
  });

  it('labels an explicitly requested historical list and releases subscriptions on destruction', () => {
    params.next(convertToParamMap({ view: 'history', page: '2' }));
    const fixture = TestBed.createComponent(DashboardRelatedComponent);
    fixture.detectChanges(); response.next({ ...page(), view:'history' }); fixture.detectChanges();
    expect(api.getRelated).toHaveBeenCalledWith('workorders', jasmine.objectContaining({ view:'history', page:2 }));
    expect(fixture.nativeElement.textContent).toContain('Histórico de Workorders');
    fixture.destroy(); expect(response.observers.length).toBe(0);
  });

  it('does not label an old or mismatched response as a current list', () => {
    const fixture = TestBed.createComponent(DashboardRelatedComponent);
    fixture.detectChanges(); response.next({ ...page(), view:'history' }); fixture.detectChanges();
    expect(fixture.componentInstance.items()).toEqual([]);
    expect(fixture.nativeElement.querySelector('[data-state="unavailable"]')).not.toBeNull();
  });

  it('navigates pages without dropping the current mode or URL filters', () => {
    const router = TestBed.inject(Router);
    const navigate = spyOn(router, 'navigate').and.resolveTo(true);
    const fixture = TestBed.createComponent(DashboardRelatedComponent);
    fixture.detectChanges(); response.next(page());
    fixture.componentInstance.changePage(2);
    expect(navigate).toHaveBeenCalledWith([], jasmine.objectContaining({ queryParams:{view:'current',page:2},queryParamsHandling:'merge' }));
  });

  it('cancels a pending request on invalid period without querying a wider scope', () => {
    const fixture = TestBed.createComponent(DashboardRelatedComponent);
    fixture.detectChanges(); const calls = api.getRelated.calls.count();
    params.next(convertToParamMap({ dateFrom:'invalid' })); fixture.detectChanges();
    expect(api.getRelated.calls.count()).toBe(calls);
    expect(response.observers.length).toBe(0);
    expect(fixture.componentInstance.items()).toEqual([]);
  });
});

function page(): IndicatorRelatedPage {
  return { items: [{ identifier:'WO-1',execution_id:'execution-old',organization_id:'org-1',organization_name:'Synthetic A',snapshot_id:17,status:'consolidated',occurred_at:'2026-08-10T12:00:00Z',updated_at:'2026-08-11T12:00:00Z' }], pagination:{page:1,pages:1,total:1},entity:'workorders',view:'current',scope:{permissions:['dashboard.read','business.read'],organization_ids:['org-1']} };
}
