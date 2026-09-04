import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, UrlTree, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject, Subject } from 'rxjs';

import { OperationalSearchPage } from './query.models';
import { OperationalSearchComponent } from './operational-search.component';
import { QueryService } from './query.service';

describe('OperationalSearchComponent', () => {
  let fixture: ComponentFixture<OperationalSearchComponent>;
  let response: Subject<OperationalSearchPage>;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let router: jasmine.SpyObj<Router>;

  beforeEach(async () => {
    response = new Subject<OperationalSearchPage>();
    params = new BehaviorSubject(convertToParamMap({ type: 'workorder', query: '000123', page: '1', pageSize: '10', sort: 'updated_desc' }));
    router = jasmine.createSpyObj<Router>('Router', ['navigate', 'navigateByUrl', 'createUrlTree', 'serializeUrl'], { url: '/search?type=workorder&query=000123&page=1&pageSize=10&sort=updated_desc', events: new Subject() });
    router.navigate.and.resolveTo(true);
    router.createUrlTree.and.returnValue({} as UrlTree);
    router.serializeUrl.and.returnValue('/synthetic-link');
    await TestBed.configureTestingModule({
      imports: [OperationalSearchComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { queryParamMap: params.asObservable() } },
        { provide: Router, useValue: router },
        { provide: QueryService, useValue: { search: () => response.asObservable() } }
      ]
    }).compileComponents();
    fixture = TestBed.createComponent(OperationalSearchComponent);
    fixture.detectChanges();
  });

  it('renders scoped context and keeps leading zeroes in links', () => {
    response.next(page()); fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('000123');
    expect(text).toContain('exec-001');
    expect(text).toContain('synergia.operational');
    expect(text).toContain('04/09/2026');
  });

  it('preserves all filters when changing page', () => {
    response.next(page()); fixture.detectChanges();
    fixture.componentInstance.changePage(2);
    expect(router.navigate).toHaveBeenCalledWith([], jasmine.objectContaining({ queryParams: { type: 'workorder', query: '000123', page: 2, pageSize: 10, sort: 'updated_desc' } }));
  });

  it('distinguishes an existing empty response from an error', () => {
    response.next({ ...page(), items: [], pagination: { page: 1, page_size: 10, total: 0, pages: 0 } }); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Nenhum resultado');
    expect(fixture.nativeElement.querySelector('[data-state="error"]')).toBeNull();
  });
});

function page(): OperationalSearchPage { return { items: [{ entity_type:'workorder',identifier:'000123',execution_id:'exec-001',workorder_number:'000123',lot_number:null,serial_number:null,organization_code:'ORG-1',processing_status:'consolidated',updated_at:'2026-09-04T12:00:00Z' }],pagination:{page:1,page_size:10,total:1,pages:1},sort:'updated_desc',entity_type:'workorder',query:'000123',source:'synergia.operational',generated_at:'2026-09-04T12:00:00Z' }; }
