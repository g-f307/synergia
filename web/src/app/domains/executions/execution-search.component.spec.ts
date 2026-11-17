import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, UrlTree, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject, Subject } from 'rxjs';
import { map } from 'rxjs';
import { executionAggregate } from '../../../testing/execution-fixtures';

import { ExecutionAggregate, ExecutionCatalogFilters, ExecutionCatalogItem, Page } from './execution.models';
import { ExecutionSearchComponent } from './execution-search.component';
import { ExecutionService } from './execution.service';

describe('ExecutionSearchComponent', () => {
  let fixture: ComponentFixture<ExecutionSearchComponent>;
  let response: Subject<Page<ExecutionCatalogItem> & { generated_at: string }>;
  let currentResponse: typeof response;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let requested: ExecutionCatalogFilters[];
  let summaryOverride: ExecutionAggregate | undefined;

  beforeEach(async () => {
    response = new Subject<Page<ExecutionCatalogItem> & { generated_at: string }>();
    currentResponse = response; requested = []; summaryOverride = undefined;
    params = new BehaviorSubject(convertToParamMap({}));
    const router = jasmine.createSpyObj<Router>('Router', ['navigate', 'createUrlTree', 'serializeUrl', 'getCurrentNavigation'], { url: '/executions' });
    router.navigate.and.resolveTo(true);
    router.getCurrentNavigation.and.returnValue(null);
    router.createUrlTree.and.returnValue({} as UrlTree);
    router.serializeUrl.and.returnValue('/executions/exec-1');
    await TestBed.configureTestingModule({
      imports: [ExecutionSearchComponent],
      providers: [
        provideRouter([]),
        { provide: Router, useValue: router },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: convertToParamMap({}) }, queryParamMap: params.asObservable() } },
        { provide: ExecutionService, useValue: { frame: (filters: ExecutionCatalogFilters) => {
          requested.push(filters);
          return currentResponse.pipe(map(page => {
            const summary = summaryOverride ?? executionAggregate({ completed: page.pagination.total }, { generated_at: page.generated_at });
            return { page, summary: { ...summary, filters: { ...summary.filters, source: filters.source ?? null, organization_id: filters.organizationId ?? null, date_from: filters.dateFrom ?? null, date_to: filters.dateTo ?? null, outcome: filters.outcome ?? null } } };
          }));
        } } }
      ]
    }).compileComponents();
    fixture = TestBed.createComponent(ExecutionSearchComponent);
    fixture.detectChanges();
  });

  it('uses the shared screen frame without repeating the visible page title', () => {
    const element = fixture.nativeElement as HTMLElement;
    const frame = element.querySelector('.execution-catalog') as HTMLElement;

    expect(getComputedStyle(frame).borderRadius).toBe('28px');
    expect(element.querySelector('h1.sr-only')).not.toBeNull();
    expect(element.querySelector('.eyebrow')).toBeNull();
    expect(element.querySelector('.page-subtitle')).toBeNull();
  });

  it('keeps the complete filter set in a compact accessible disclosure', () => {
    const element = fixture.nativeElement as HTMLElement;
    const disclosure = element.querySelector('details.catalog-filters') as HTMLDetailsElement;
    const toggleIcon = element.querySelector('.filter-toggle-icon');
    const controls = [...element.querySelectorAll('.filters input, .filters select')] as Array<HTMLInputElement | HTMLSelectElement>;

    expect(disclosure).not.toBeNull();
    expect(disclosure.open).toBeFalse();
    expect(toggleIcon?.getAttribute('aria-hidden')).toBe('true');
    expect(controls.length).toBe(9);
    expect(element.querySelectorAll('.filter-field').length).toBe(9);
    expect(controls.every((control) => !!control.id && !!control.getAttribute('name'))).toBeTrue();
    expect(controls.every((control) => element.querySelector(`label[for="${control.id}"]`))).toBeTrue();
  });

  it('places the results heading before the filters in reading order', () => {
    const element = fixture.nativeElement as HTMLElement;
    const heading = element.querySelector('.results-heading') as HTMLElement;
    const filters = element.querySelector('.catalog-filters') as HTMLElement;
    expect(heading.compareDocumentPosition(filters) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('shows the result count and catalog generation time with the same hierarchy as pending items', () => {
    response.next({
      items: [],
      pagination: { page: 1, page_size: 20, total: 16, pages: 1 },
      sort: 'newest',
      generated_at: '2026-10-19T07:40:00Z'
    });
    fixture.detectChanges();

    const heading = fixture.nativeElement.querySelector('.results-heading') as HTMLElement;
    expect(heading.textContent).toContain('Execuções encontradas');
    expect(heading.textContent).toContain('16 resultado(s)');
    expect(heading.querySelector('time')?.getAttribute('datetime')).toBe('2026-10-19T07:40:00Z');
    expect(heading.querySelector('time')?.textContent).toContain('19/10/2026');
  });

  it('renders execution results as readable operational rows', () => {
    response.next({
      items: [{ execution_id: 'exec-1', organization_id: 'org-1', status: 'completed', outcome: 'completed', lifecycle: 'completed', attempt: 1, source: 'N-FP', file_types: ['xlsx'], file_count: 1, rows_read: 240, error_count: 0, warning_count: 2, started_at: '2026-10-15T12:00:00Z', finished_at: '2026-10-15T12:02:00Z' }],
      pagination: { page: 1, page_size: 20, total: 1, pages: 1 }, sort: 'newest', generated_at: '2026-10-19T07:40:00Z'
    });
    fixture.detectChanges();
    const row = fixture.nativeElement.querySelector('.execution-row') as HTMLButtonElement;

    expect(row).not.toBeNull();
    expect(row.textContent).toContain('exec-1');
    expect(row.querySelector('.status-pill')).not.toBeNull();
    expect(getComputedStyle(row).color).not.toBe('rgb(255, 255, 255)');
  });

  it('uses the aggregate categories instead of recounting the visible page', () => {
    summaryOverride = executionAggregate({ completed: 3, partial: 2, skipped_duplicate: 9 });
    response.next({ items: [], pagination: { page: 1, page_size: 1, total: 14, pages: 14 }, sort: 'newest', generated_at: '2026-10-27T03:00:00Z' });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-outcome="completed"] dd')?.textContent).toBe('3');
    expect(fixture.nativeElement.querySelector('[data-outcome="partial"] dd')?.textContent).toBe('2');
    expect(fixture.nativeElement.querySelector('[data-outcome="skipped_duplicate"] dd')?.textContent).toBe('9');
    expect(fixture.nativeElement.querySelector('.results-heading')?.textContent).toContain('14');
  });

  it('restores canonical filters through URL changes without losing microseconds', () => {
    params.next(convertToParamMap({ source: 'OWM', outcome: 'skipped_duplicate', date_to: '2026-11-02T03:59:59.999999Z', page: '2' }));
    expect(requested.at(-1)?.source).toBe('OWM');
    expect(requested.at(-1)?.outcome).toBe('skipped_duplicate');
    expect(requested.at(-1)?.dateTo).toBe('2026-11-02T03:59:59.999999Z');
    expect(requested.at(-1)?.page).toBe(2);
    params.next(convertToParamMap({}));
    expect(requested.at(-1)?.source).toBeUndefined();
    expect(requested.at(-1)?.page).toBe(1);
    expect(fixture.componentInstance.source()).toBe('');
  });

  it('cancels an in-flight frame on invalid URL and shows its error outside the disclosure', () => {
    params.next(convertToParamMap({ date_from: 'invalid' }));
    response.next({ items: [], pagination: { page: 1, page_size: 20, total: 99, pages: 5 }, sort: 'newest', generated_at: '2026-10-27T03:00:00Z' });
    fixture.detectChanges();
    expect(fixture.componentInstance.summary()).toBeNull();
    expect(fixture.nativeElement.querySelector('details [role="alert"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).toContain('período válido');
    expect(fixture.nativeElement.querySelector('#execution-date-from')?.getAttribute('aria-invalid')).toBe('true');
    expect(fixture.nativeElement.querySelector('#execution-date-from')?.getAttribute('aria-describedby')).toBe('execution-period-error');
    fixture.componentInstance.load(1);
    expect(requested.length).toBe(1);
    params.next(convertToParamMap({}));
    expect(requested.length).toBe(2);
  });

  it('preserves legacy lifecycle links without converting their meaning to outcome', () => {
    params.next(convertToParamMap({ lifecycle: 'completed' }));
    expect(requested.at(-1)?.lifecycle).toBe('completed');
    expect(requested.at(-1)?.outcome).toBeUndefined();
  });

  it('retains a legacy lifecycle when applying another filter without selecting an outcome', () => {
    params.next(convertToParamMap({ lifecycle: 'completed', date_to: '2026-11-02T03:59:59.999999Z' }));
    fixture.componentInstance.source.set('OWM');
    fixture.componentInstance.apply(new Event('submit'));
    expect(requested.at(-1)?.lifecycle).toBe('completed');
    expect(requested.at(-1)?.outcome).toBeUndefined();
    expect(requested.at(-1)?.dateTo).toBe('2026-11-02T03:59:59.999999Z');
  });

  it('replaces the legacy lifecycle filter when the user selects a canonical outcome', () => {
    params.next(convertToParamMap({ lifecycle: 'completed' }));
    fixture.componentInstance.outcome.set('partial');
    fixture.componentInstance.apply(new Event('submit'));
    expect(requested.at(-1)?.outcome).toBe('partial');
    expect(requested.at(-1)?.lifecycle).toBeUndefined();
    fixture.componentInstance.source.set('OWM');
    fixture.componentInstance.apply(new Event('submit'));
    expect(requested.at(-1)?.lifecycle).toBeUndefined();
  });

  it('keeps the last complete frame after a filter request fails', () => {
    const page = { items: [], pagination: { page: 1, page_size: 20, total: 14, pages: 1 }, sort: 'newest', generated_at: '2026-10-27T03:00:00Z' };
    response.next(page); fixture.detectChanges();
    currentResponse = new Subject(); fixture.componentInstance.source.set('OWM');
    fixture.componentInstance.apply(new Event('submit')); currentResponse.error(new Error('offline')); fixture.detectChanges();
    expect(fixture.componentInstance.summary()?.total).toBe(14);
    expect(fixture.componentInstance.summary()?.filters.source).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('últimos dados obtidos e seu recorte');
  });

  it('does not cancel another navigation when a pending frame completes', () => {
    const router = TestBed.inject(Router) as jasmine.SpyObj<Router>;
    router.getCurrentNavigation.and.returnValue({ id: 10 } as NonNullable<ReturnType<Router['getCurrentNavigation']>>);
    response.next({ items: [], pagination: { page: 1, page_size: 20, total: 14, pages: 1 }, sort: 'newest', generated_at: '2026-10-27T03:00:00Z' });
    expect(fixture.componentInstance.summary()?.total).toBe(14);
    expect(router.navigate).not.toHaveBeenCalled();
  });

  it('removes catalog rows and totals after authorization is revoked', () => {
    response.next({ items: [], pagination: { page: 1, page_size: 20, total: 14, pages: 1 }, sort: 'newest', generated_at: '2026-10-27T03:00:00Z' });
    currentResponse = new Subject(); fixture.componentInstance.load(1);
    currentResponse.error({ kind: 'forbidden', status: 403 }); fixture.detectChanges();
    expect(fixture.componentInstance.summary()).toBeNull();
    expect(fixture.nativeElement.querySelector('.outcome-totals')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Acesso proibido');
  });

  it('scrolls filters, results and pagination together inside the screen frame', () => {
    response.next({
      items: Array.from({ length: 20 }, (_, index) => ({ execution_id: `exec-${index}`, organization_id: 'org-1', status: 'completed', outcome: 'completed' as const, lifecycle: 'completed' as const, attempt: 1, source: 'N-FP', file_types: ['xlsx'], file_count: 1, rows_read: 10, error_count: 0, warning_count: 0, started_at: '2026-10-15T12:00:00Z', finished_at: '2026-10-15T12:02:00Z' })),
      pagination: { page: 1, page_size: 20, total: 21, pages: 2 }, sort: 'newest', generated_at: '2026-10-19T07:40:00Z'
    });
    fixture.detectChanges();

    const results = fixture.nativeElement.querySelector('.results') as HTMLElement;
    const content = fixture.nativeElement.querySelector('.catalog-content') as HTMLElement;
    const frame = fixture.nativeElement.querySelector('.execution-catalog') as HTMLElement;

    expect(getComputedStyle(frame).overflowY).toBe('auto');
    expect(getComputedStyle(results).overflowY).toBe('visible');
    expect(getComputedStyle(content).overflowY).toBe('visible');
    expect(fixture.nativeElement.querySelector('syn-pagination')).not.toBeNull();
  });
});
