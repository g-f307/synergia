import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, UrlTree, convertToParamMap, provideRouter } from '@angular/router';
import { Subject } from 'rxjs';

import { ExecutionCatalogItem, Page } from './execution.models';
import { ExecutionSearchComponent } from './execution-search.component';
import { ExecutionService } from './execution.service';

describe('ExecutionSearchComponent', () => {
  let fixture: ComponentFixture<ExecutionSearchComponent>;
  let response: Subject<Page<ExecutionCatalogItem> & { generated_at: string }>;

  beforeEach(async () => {
    response = new Subject<Page<ExecutionCatalogItem> & { generated_at: string }>();
    const router = jasmine.createSpyObj<Router>('Router', ['navigate', 'createUrlTree', 'serializeUrl'], { url: '/executions' });
    router.navigate.and.resolveTo(true);
    router.createUrlTree.and.returnValue({} as UrlTree);
    router.serializeUrl.and.returnValue('/executions/exec-1');
    await TestBed.configureTestingModule({
      imports: [ExecutionSearchComponent],
      providers: [
        provideRouter([]),
        { provide: Router, useValue: router },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: convertToParamMap({}) } } },
        { provide: ExecutionService, useValue: { list: () => response.asObservable() } }
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
      items: [{ execution_id: 'exec-1', organization_id: 'org-1', status: 'completed', lifecycle: 'completed', attempt: 1, source: 'N-FP', file_types: ['xlsx'], file_count: 1, rows_read: 240, error_count: 0, warning_count: 2, started_at: '2026-10-15T12:00:00Z', finished_at: '2026-10-15T12:02:00Z' }],
      pagination: { page: 1, page_size: 20, total: 1, pages: 1 }, sort: 'newest', generated_at: '2026-10-19T07:40:00Z'
    });
    fixture.detectChanges();
    const row = fixture.nativeElement.querySelector('.execution-row') as HTMLButtonElement;

    expect(row).not.toBeNull();
    expect(row.textContent).toContain('exec-1');
    expect(row.querySelector('.status-pill')).not.toBeNull();
    expect(getComputedStyle(row).color).not.toBe('rgb(255, 255, 255)');
  });

  it('scrolls filters, results and pagination together inside the screen frame', () => {
    response.next({
      items: Array.from({ length: 20 }, (_, index) => ({ execution_id: `exec-${index}`, organization_id: 'org-1', status: 'completed', lifecycle: 'completed' as const, attempt: 1, source: 'N-FP', file_types: ['xlsx'], file_count: 1, rows_read: 10, error_count: 0, warning_count: 0, started_at: '2026-10-15T12:00:00Z', finished_at: '2026-10-15T12:02:00Z' })),
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
