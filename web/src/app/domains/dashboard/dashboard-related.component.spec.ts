import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { DashboardRelatedComponent } from './dashboard-related.component';
import { DashboardService } from './dashboard.service';

describe('DashboardRelatedComponent', () => {
  it('uses organization and period received from the card URL', async () => {
    const getRelated = jasmine.createSpy('getRelated').and.returnValue(of({ items: [{ identifier: 'WO-1', status: 'consolidated', occurred_at: '2026-08-10T12:00:00Z' }], pagination: { page: 1, pages: 1, total: 1 }, entity: 'workorders' }));
    await TestBed.configureTestingModule({
      imports: [DashboardRelatedComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ entity: 'workorders' }), queryParamMap: convertToParamMap({ organization: 'org-1', dateFrom: '2026-08-01', dateTo: '2026-08-31' }) } } },
        { provide: DashboardService, useValue: { getRelated } }
      ]
    }).compileComponents();
    const fixture = TestBed.createComponent(DashboardRelatedComponent);
    fixture.detectChanges();

    expect(getRelated).toHaveBeenCalledWith('workorders', { organizationId: 'org-1', dateFrom: '2026-08-01', dateTo: '2026-08-31', page: 1 });
    expect(fixture.nativeElement.textContent).toContain('WO-1');
    expect(fixture.nativeElement.textContent).toContain('org-1');
    expect(fixture.nativeElement.textContent).toContain('01/08/2026');
    const row = fixture.nativeElement.querySelector('.workorder-row') as HTMLAnchorElement;
    expect(row.getAttribute('href')).toContain('/workorders/WO-1');
    expect(row.querySelector('.status-pill')?.textContent).toContain('Consolidada');
    expect(row.querySelector('.row-chevron')).not.toBeNull();
  });

  it('reads the page from the URL and renders pagination metadata', async () => {
    const getRelated = jasmine.createSpy('getRelated').and.returnValue(of({ items: [{ identifier: 'WO-26', status: 'consolidated', occurred_at: '2026-08-10T12:00:00Z' }], pagination: { page: 2, pages: 3, total: 51 }, entity: 'workorders' }));
    await TestBed.configureTestingModule({
      imports: [DashboardRelatedComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ entity: 'workorders' }), queryParamMap: convertToParamMap({ page: '2' }) } } },
        { provide: DashboardService, useValue: { getRelated } }
      ]
    }).compileComponents();
    const fixture = TestBed.createComponent(DashboardRelatedComponent);
    fixture.detectChanges();

    expect(getRelated).toHaveBeenCalledWith('workorders', { organizationId: '', dateFrom: '', dateTo: '', page: 2 });
    expect(fixture.nativeElement.textContent).toContain('51');
    expect(fixture.nativeElement.querySelector('syn-pagination')).not.toBeNull();
    const page = fixture.nativeElement.querySelector('.workorders-page') as HTMLElement;
    const body = fixture.nativeElement.querySelector('.workorders-body') as HTMLElement;
    expect(getComputedStyle(page).overflow).toBe('hidden');
    expect(getComputedStyle(body).overflowY).toBe('auto');
    const heading = fixture.nativeElement.querySelector('.results-heading') as HTMLElement;
    expect(heading.firstElementChild?.classList).toContain('back-link');
    expect(getComputedStyle(heading).display).toBe('grid');
    expect(getComputedStyle(heading).justifyItems).toBe('start');
    expect(getComputedStyle(fixture.nativeElement.querySelector('.workorder-list')).overflow).toBe('visible');
    expect(fixture.nativeElement.querySelector('.eyebrow')).toBeNull();
    expect(fixture.nativeElement.querySelector('table')).toBeNull();
  });
});
