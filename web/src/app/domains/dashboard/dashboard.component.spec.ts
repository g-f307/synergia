import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { Subject } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { Indicators } from '../../shared/api/operational.models';
import { DashboardComponent } from './dashboard.component';
import { DashboardService } from './dashboard.service';

describe('DashboardComponent', () => {
  let fixture: ComponentFixture<DashboardComponent>;
  let response: Subject<Indicators>;
  let currentResponse: Subject<Indicators>;
  let requestedFilters: unknown[];
  const profile = signal<{ permissions: Array<{ key: string; organizations: string[] | null }> }>({ permissions: [{ key: 'dashboard.read', organizations: ['org-synthetic'] }] });

  beforeEach(async () => {
    document.documentElement.dataset['fontScale'] = 'normal';
    profile.set({ permissions: [{ key: 'dashboard.read', organizations: ['org-synthetic'] }] });
    response = new Subject<Indicators>();
    currentResponse = response;
    requestedFilters = [];
    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideRouter([]),
        { provide: DashboardService, useValue: { getIndicators: (filters: unknown) => { requestedFilters.push(filters); return currentResponse.asObservable(); } } },
        { provide: SessionService, useValue: { profile } }
      ]
    }).compileComponents();
    fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();
  });

  it('renders complete persisted aggregates and their origin', () => {
    response.next(completeIndicators());
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;

    expect(text).not.toContain('Visão geral operacional');
    expect(fixture.nativeElement.querySelector('h1.sr-only')?.textContent).toContain('Visão geral');
    expect(text).toContain('Liberações parciais');
    expect(text).toContain('Concluídas: 2');
    expect(text).toContain('Em aberto: 2');
    expect(text).toContain('Planejada');
    expect(fixture.nativeElement.querySelectorAll('.metric').length).toBe(3);
    const badges = [...fixture.nativeElement.querySelectorAll('.metric-badge img')] as HTMLImageElement[];
    expect(badges.map((badge) => badge.getAttribute('src'))).toEqual([
      '/assets/icons/run.svg',
      '/assets/icons/production.svg',
      '/assets/icons/queue.svg'
    ]);
    expect(badges.every((badge) => badge.getAttribute('aria-hidden') === 'true')).toBeTrue();
    const badgeContainers = [...fixture.nativeElement.querySelectorAll('.metric-badge')] as HTMLElement[];
    expect(new Set(badgeContainers.map((badge) => getComputedStyle(badge).backgroundColor)).size).toBe(1);
    expect(badges.every((badge) => getComputedStyle(badge).filter === 'none')).toBeTrue();
    expect(fixture.nativeElement.querySelector('syn-state')).toBeNull();
  });

  it('renders compact filters and charts from persisted aggregates', () => {
    response.next(completeIndicators());
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('details.dashboard-filters')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.execution-chart')).not.toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.quantity-bar').length).toBe(4);
    expect(fixture.nativeElement.querySelector('.status-donut')).not.toBeNull();
    expect((fixture.nativeElement.querySelector('.status-donut') as HTMLElement).style.background).toContain('conic-gradient');
    const quantityColors = [...fixture.nativeElement.querySelectorAll('.quantity-bar .bar-track span')]
      .map((element) => (element as HTMLElement).style.backgroundColor);
    expect(new Set(quantityColors).size).toBe(4);
    expect(fixture.nativeElement.querySelector('.context')).toBeNull();
    expect(fixture.nativeElement.querySelector('.eyebrow')).toBeNull();
  });

  it('offers an accessible quick search above the calculation timestamp', () => {
    response.next(completeIndicators());
    fixture.detectChanges();

    const header = fixture.nativeElement.querySelector('.page-header') as HTMLElement;
    const search = header.querySelector('form.dashboard-search') as HTMLFormElement;
    const input = search?.querySelector('input') as HTMLInputElement;
    const type = search?.querySelector('select') as HTMLSelectElement;
    const updated = header.querySelector('.updated') as HTMLElement;

    expect(search).not.toBeNull();
    expect(input?.placeholder).toContain('lote');
    expect(input?.getAttribute('aria-label')).toContain('lote');
    expect([...type.options].map((option) => option.value)).toEqual(['workorder', 'lot', 'serial']);
    expect(search.compareDocumentPosition(updated) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(getComputedStyle(header).alignItems).toBe('flex-start');
  });

  it('opens the operational search with the selected type and trimmed term', () => {
    response.next(completeIndicators());
    fixture.detectChanges();
    const router = TestBed.inject(Router);
    const navigate = spyOn(router, 'navigate').and.resolveTo(true);
    const form = fixture.nativeElement.querySelector('form.dashboard-search') as HTMLFormElement;
    const input = form.querySelector('input') as HTMLInputElement;
    const type = form.querySelector('select') as HTMLSelectElement;

    input.value = '  LOT-2026-42  ';
    input.dispatchEvent(new Event('input'));
    type.value = 'lot';
    type.dispatchEvent(new Event('change'));
    form.dispatchEvent(new Event('submit'));

    expect(navigate).toHaveBeenCalledWith(['/search'], {
      queryParams: { type: 'lot', query: 'LOT-2026-42', page: 1, pageSize: 25, sort: 'updated_desc' }
    });
  });

  it('keeps the dashboard frame fixed and scrolls only its data surface', () => {
    response.next(completeIndicators());
    fixture.detectChanges();
    const dashboard = fixture.nativeElement.querySelector('.dashboard') as HTMLElement;
    const surface = fixture.nativeElement.querySelector('.dashboard-surface') as HTMLElement;

    expect(getComputedStyle(dashboard).overflow).toBe('hidden');
    expect(getComputedStyle(surface).overflowY).toBe('auto');
  });

  it('scales computed indicator and support text sizes with the large preference', () => {
    response.next(completeIndicators());
    fixture.detectChanges();
    const value = fixture.nativeElement.querySelector('.indicator-value') as HTMLElement;
    const detail = fixture.nativeElement.querySelector('.indicator-detail') as HTMLElement;
    const normalValue = Number.parseFloat(getComputedStyle(value).fontSize);
    const normalDetail = Number.parseFloat(getComputedStyle(detail).fontSize);

    document.documentElement.dataset['fontScale'] = 'large';

    expect(Number.parseFloat(getComputedStyle(value).fontSize)).toBeGreaterThan(normalValue);
    expect(Number.parseFloat(getComputedStyle(detail).fontSize)).toBeGreaterThan(normalDetail);
  });

  it('distinguishes an explicit empty result from absent data', () => {
    response.next({ ...completeIndicators(), executions: {}, workorders: { total: 0, partially_released: 0 }, pending_items: {}, quantities: { planned: 0, produced: 0, received: 0, released: 0 } });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Nenhum registro no escopo');
    expect(fixture.nativeElement.textContent).not.toContain('Ausente');
  });

  it('marks a response with a missing aggregate as partial instead of zero', () => {
    const partial = completeIndicators();
    delete partial.quantities.released;
    response.next(partial);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toContain('Resultado parcial');
    expect(fixture.nativeElement.querySelector('.partial-note')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Ausente');
  });

  it('renders explicit null quantity as absent without treating zero as absent', () => {
    const partial = completeIndicators();
    partial.quantities.planned = null;
    partial.quantities.produced = 0;
    response.next(partial);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toContain('Resultado parcial');
    expect(fixture.nativeElement.querySelector('.partial-note')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Ausente');
    expect(fixture.nativeElement.textContent).toContain('Produzida');
  });

  it('renders forbidden without operational numbers', () => {
    response.error(failure('forbidden', 403));
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Acesso proibido');
    expect(fixture.nativeElement.querySelector('.indicator-grid')).toBeNull();
  });

  it('renders source unavailability separately and offers retry', () => {
    response.error(failure('unavailable', 503));
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Indicadores indisponíveis');
    expect(fixture.nativeElement.querySelector('syn-state button')).not.toBeNull();
  });

  it('keeps organization and period filters accessible for a global profile', () => {
    profile.set({ permissions: [{ key: 'dashboard.read', organizations: null }] });
    response.next(completeIndicators());
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[aria-labelledby="dashboard-title"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelectorAll('label').length).toBe(3);
  });

  it('routes each dashboard metric to its canonical destination with compatible filters', async () => {
    response.next(completeIndicators());
    fixture.componentInstance.organizationId.set('org-synthetic');
    fixture.componentInstance.dateFrom.set('2026-08-01');
    fixture.componentInstance.dateTo.set('2026-08-31');
    fixture.componentInstance.applyFilters(new Event('submit'));
    await fixture.whenStable();
    response.next(completeIndicators());
    fixture.detectChanges();

    expect(requestedFilters.at(-1)).toEqual({ organizationId: 'org-synthetic', dateFrom: '2026-08-01', dateTo: '2026-08-31' });
    const hrefs = [...fixture.nativeElement.querySelectorAll('.metric a')]
      .map((link) => (link as HTMLAnchorElement).getAttribute('href') ?? '');
    expect(hrefs[0]).toContain('/executions');
    expect(hrefs[0]).toContain('organization_id=org-synthetic');
    expect(hrefs[0]).toContain('date_from=2026-08-01');
    expect(hrefs[0]).toContain('date_to=2026-08-31');
    expect(hrefs[1]).toContain('/dashboard/related/workorders');
    expect(hrefs[1]).toContain('organization=org-synthetic');
    expect(hrefs[2]).toContain('/pending-items');
    expect(hrefs[2]).toContain('status=open');
    expect(hrefs.every((href) => !href.includes('/dashboard/related/executions'))).toBeTrue();
    expect(hrefs.every((href) => !href.includes('/dashboard/related/pending-items'))).toBeTrue();
  });

  it('rejects an inverted period before requesting data', () => {
    fixture.componentInstance.dateFrom.set('2026-09-01');
    fixture.componentInstance.dateTo.set('2026-08-01');
    fixture.componentInstance.applyFilters(new Event('submit'));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).toContain('data inicial');
    expect(requestedFilters.length).toBe(1);
  });

  it('ignores an older response completed after the current filter request', () => {
    const newer = new Subject<Indicators>();
    currentResponse = newer;
    fixture.componentInstance.dateFrom.set('2026-09-01');
    fixture.componentInstance.load();
    response.next({ ...completeIndicators(), workorders: { total: 999, partially_released: 0 } });
    newer.next({ ...completeIndicators(), workorders: { total: 7, partially_released: 0 } });
    fixture.detectChanges();
    const values = [...fixture.nativeElement.querySelectorAll('.indicator-value')].map((node: Element) => node.textContent?.trim());
    expect(values).toContain('7');
    expect(values).not.toContain('999');
  });
});

function completeIndicators(): Indicators {
  return { generated_at: '2026-09-03T12:00:00Z', source: 'synergia.operational', organizations: [{ id: 'org-synthetic', code: 'syn-org', name: 'Organização sintética' }], filters: { organization_id: null, date_from: null, date_to: null }, executions: { completed: 2, failed: 1 }, workorders: { total: 4, partially_released: 1 }, pending_items: { open: 2 }, quantities: { planned: 20, produced: 15, received: 12, released: 10 } };
}

function failure(kind: ApiFailure['kind'], status: number): ApiFailure {
  return { kind, status, code: 'synthetic', message: 'synthetic', correlationId: null, fields: [] };
}
