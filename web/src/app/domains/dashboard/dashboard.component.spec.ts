import { completeQuantityCoverage } from '../../../testing/indicator-fixtures';
import { I18nService } from '../../shared/i18n/i18n.service';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { BehaviorSubject, Subject, map } from 'rxjs';
import { executionAggregate } from '../../../testing/execution-fixtures';
import { ExecutionScopeFilters } from '../executions/execution.models';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { Indicators } from '../../shared/api/operational.models';
import { DashboardComponent } from './dashboard.component';
import { DashboardService } from './dashboard.service';

describe('DashboardComponent', () => {
  let fixture: ComponentFixture<DashboardComponent>;
  let response: Subject<Indicators>;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let currentResponse: Subject<Indicators>;
  let requestedFilters: unknown[];
  const profile = signal<{ permissions: Array<{ key: string; organizations: string[] | null }> }>({ permissions: [{ key: 'dashboard.read', organizations: ['org-synthetic'] }, { key: 'business.read', organizations: ['org-synthetic'] }] });

  beforeEach(async () => {
    document.documentElement.dataset['fontScale'] = 'normal';
    profile.set({ permissions: [{ key: 'dashboard.read', organizations: ['org-synthetic'] }, { key: 'business.read', organizations: ['org-synthetic'] }] });
    response = new Subject<Indicators>();
    currentResponse = response;
    requestedFilters = [];
    params = new BehaviorSubject(convertToParamMap({}));
    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { queryParamMap: params.asObservable() } },
        { provide: DashboardService, useValue: { getIndicators: (filters: ExecutionScopeFilters) => { requestedFilters.push(filters); return currentResponse.pipe(map(data => ({ ...data, execution_summary: data.execution_summary ? { ...data.execution_summary, filters: { ...data.execution_summary.filters, organization_id: filters.organizationId ?? null, source: filters.source ?? null, file_type: filters.fileType ?? null, date_from: filters.dateFrom ?? null, date_to: filters.dateTo ?? null } } : data.execution_summary }))); } } },
        { provide: SessionService, useValue: { profile } }
      ]
    }).compileComponents();
    fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();
  });

  it('retains a legacy lifecycle when applying another filter without selecting an outcome', () => {
    params.next(convertToParamMap({ lifecycle: 'completed', date_to: '2026-11-02T03:59:59.999999Z' }));
    fixture.componentInstance.source.set('OWM');
    fixture.componentInstance.applyFilters(new Event('submit'));
    expect(requestedFilters.at(-1)).toEqual(jasmine.objectContaining({ lifecycle: 'completed', dateTo: '2026-11-02T03:59:59.999999Z' }));
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

  it('cancels an in-flight response for an invalid URL and does not refresh a wider scope', () => {
    params.next(convertToParamMap({ date_to: 'invalid' }));
    response.next(completeIndicators()); fixture.detectChanges();
    expect(fixture.componentInstance.data()).toBeNull();
    expect(fixture.componentInstance.state()).toBe('error');
    expect(fixture.nativeElement.querySelector('details [role="alert"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).toContain('período válido');
    fixture.componentInstance.load();
    expect(requestedFilters.length).toBe(1);
    params.next(convertToParamMap({}));
    expect(requestedFilters.length).toBe(2);
  });

  it('reconciles 3 completed, 2 partial and 9 duplicates without using legacy counts', () => {
    response.next({ ...completeIndicators(), executions: { completed: 999, duplicate: 999 }, execution_summary: executionAggregate({ completed: 3, partial: 2, skipped_duplicate: 9 }, { scope: { permission: 'dashboard.read', organization_ids: ['org-synthetic'] } }) });
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.indicator-value')?.textContent).toBe('14');
    expect(element.querySelector('.indicator-detail')?.textContent).toContain('Concluídas: 3');
    const legend = element.querySelector('.status-legend')?.textContent;
    expect(legend).toContain('Com erros2');
    expect(legend).toContain('Ignoradas por duplicidade9');
    expect(element.textContent).not.toContain('999');
  });

  it('keeps the complete last dataset and its filter context when refresh fails', () => {
    response.next(completeIndicators()); fixture.detectChanges();
    currentResponse = new Subject<Indicators>();
    fixture.componentInstance.source.set('OWM');
    fixture.componentInstance.applyFilters(new Event('submit'));
    currentResponse.error(failure('unavailable', 503)); fixture.detectChanges();
    expect(fixture.componentInstance.state()).toBe('stale');
    expect(fixture.nativeElement.querySelector('.indicator-value')?.textContent).toBe('3');
    expect(fixture.componentInstance.data()?.execution_summary.filters.source).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('últimos dados obtidos e seu recorte');
  });

  it('removes the last dataset when authorization is lost', () => {
    response.next(completeIndicators()); fixture.detectChanges();
    currentResponse = new Subject<Indicators>(); fixture.componentInstance.load();
    currentResponse.error(failure('forbidden', 403)); fixture.detectChanges();
    expect(fixture.componentInstance.data()).toBeNull();
    expect(fixture.nativeElement.querySelector('.indicator-value')).toBeNull();
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
    response.next({ ...completeIndicators(), executions: {}, execution_summary: executionAggregate(), workorders: { total: 0, partially_released: 0 }, workorders_current: { total: 0, partially_released: 0 }, quantities_coverage: Object.fromEntries(['planned','produced','received','released'].map(key => [key,{known_sum:null,known_count:0,total_count:0,coverage_percent:null,state:'empty'}])) as Indicators['quantities_coverage'], pending_items: {}, quantities: { planned: 0, produced: 0, received: 0, released: 0 } });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Nenhum registro no escopo');
    expect(fixture.nativeElement.textContent).not.toContain('Ausente');
  });

  it('marks a response with a missing aggregate as partial instead of zero', () => {
    const partial = completeIndicators();
    delete (partial.quantities_coverage as Partial<Indicators['quantities_coverage']>).released;
    response.next(partial);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toContain('Resultado parcial');
    expect(fixture.nativeElement.querySelector('.partial-note')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Cobertura indisponível');
  });

  it('renders explicit null quantity as absent without treating zero as absent', () => {
    const partial = completeIndicators();
    partial.quantities_coverage.planned = {known_sum:null,known_count:0,total_count:3,coverage_percent:0,state:'missing'};
    partial.quantities_coverage.produced = {known_sum:0,known_count:3,total_count:3,coverage_percent:100,state:'complete'};
    response.next(partial);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toContain('Resultado parcial');
    expect(fixture.nativeElement.querySelector('.partial-note')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Não informado');
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
    expect(fixture.nativeElement.querySelectorAll('label').length).toBe(6);
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

    expect(requestedFilters.at(-1)).toEqual(jasmine.objectContaining({ organizationId: 'org-synthetic', dateFrom: '2026-08-01T04:00:00Z', dateTo: '2026-09-01T03:59:59.999999Z' }));
    const hrefs = [...fixture.nativeElement.querySelectorAll('.metric a')]
      .map((link) => (link as HTMLAnchorElement).getAttribute('href') ?? '');
    expect(hrefs[0]).toContain('/executions');
    expect(hrefs[0]).toContain('organization_id=org-synthetic');
    expect(hrefs[0]).toContain('date_from=2026-08-01');
    expect(hrefs[0]).toContain('date_to=2026-09-01');
    expect(hrefs[1]).toContain('/dashboard/related/workorders');
    expect(hrefs[1]).toContain('organization_id=org-synthetic');
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
    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).toContain('período válido');
    expect(requestedFilters.length).toBe(1);
  });

  it('ignores an older response completed after the current filter request', () => {
    const newer = new Subject<Indicators>();
    currentResponse = newer;
    fixture.componentInstance.dateFrom.set('2026-09-01');
    fixture.componentInstance.load();
    response.next({ ...completeIndicators(), workorders_current: { total: 999, partially_released: 0 } });
    newer.next({ ...completeIndicators(), workorders_current: { total: 7, partially_released: 0 } });
    fixture.detectChanges();
    const values = [...fixture.nativeElement.querySelectorAll('.indicator-value')].map((node: Element) => node.textContent?.trim());
    expect(values).toContain('7');
    expect(values).not.toContain('999');
  });
  it('shows a known subtotal and current denominator instead of historical aggregates', () => {
    const data = completeIndicators();
    data.workorders = {total:999,partially_released:999};
    data.quantities = {planned:999,produced:999,received:999,released:999};
    data.quantities_coverage.planned = {known_sum:4,known_count:2,total_count:3,coverage_percent:200/3,state:'partial'};
    response.next(data); fixture.detectChanges();
    const row = fixture.nativeElement.querySelector('[data-quantity="planned"]') as HTMLElement;
    expect(row.querySelector('.known-quantity')?.textContent).toBe('4');
    expect(row.textContent).toContain('Subtotal conhecido');
    expect(row.textContent).toContain('Dados de 2 de 3 Workorders');
    expect(row.textContent).toContain('66,7%');
    expect(row.querySelector('[role="meter"]')?.getAttribute('aria-valuenow')).toBe(String(200/3));
    expect(Number.parseFloat((row.querySelector('.coverage-track span') as HTMLElement).style.width)).toBeCloseTo(200/3, 3);
    expect(fixture.nativeElement.querySelectorAll('.indicator-value')[1].textContent).toBe('3');
    expect(fixture.nativeElement.textContent).not.toContain('999');
  });

  it('shows a known zero with full coverage rather than a fabricated minimum quantity bar', () => {
    const data = completeIndicators();
    data.quantities_coverage.produced = {known_sum:0,known_count:3,total_count:3,coverage_percent:100,state:'complete'};
    response.next(data); fixture.detectChanges();
    const row = fixture.nativeElement.querySelector('[data-quantity="produced"]') as HTMLElement;
    expect(row.querySelector('.known-quantity')?.textContent).toBe('0');
    expect(row.textContent).toContain('Total conhecido');
    expect(row.textContent).toContain('100%');
    expect((row.querySelector('.coverage-track span') as HTMLElement).style.width).toBe('100%');
    expect(getComputedStyle(row.querySelector('.coverage-track span')!).minWidth).toBe('0px');
  });

  it('renders unknown quantities without numeric zero or a fictional bar', () => {
    const data = completeIndicators();
    data.quantities_coverage.received = {known_sum:null,known_count:0,total_count:3,coverage_percent:0,state:'missing'};
    response.next(data); fixture.detectChanges();
    const row = fixture.nativeElement.querySelector('[data-quantity="received"]') as HTMLElement;
    expect(row.textContent).toContain('Não informado');
    expect(row.textContent).toContain('Dados de 0 de 3 Workorders');
    expect(row.querySelector('.known-quantity')).toBeNull();
    expect(row.querySelector('[role="meter"]')).toBeNull();
  });

  it('does not show coverage percentages or quantity bars for an empty current set', () => {
    response.next({ ...completeIndicators(), workorders_current:{total:0,partially_released:0} }); fixture.detectChanges();
    const chart = fixture.nativeElement.querySelector('.quantities-chart') as HTMLElement;
    expect(chart.textContent).toContain('Sem Workorders no período');
    expect(chart.querySelector('[role="meter"]')).toBeNull();
    expect(chart.querySelector('.known-quantity')).toBeNull();
    expect(chart.textContent).not.toContain('100%');
  });

  it('rounds percentages only for display in the active locale', () => {
    const data = completeIndicators();
    data.quantities_coverage.planned = {known_sum:4,known_count:2,total_count:3,coverage_percent:200/3,state:'partial'};
    response.next(data); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-quantity="planned"]').textContent).toContain('66,7%');
    TestBed.inject(I18nService).configure('en-US'); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-quantity="planned"]').textContent).toContain('66.7%');
    expect(fixture.componentInstance.data()?.quantities_coverage.planned.coverage_percent).toBe(200/3);
    TestBed.inject(I18nService).configure('pt-BR');
  });

  for (const dashboardScope of [['org-synthetic','org-b'], null]) {
    it(`labels a narrower detail scope without changing the dashboard total (${dashboardScope === null ? 'global' : 'scoped'})`, () => {
      profile.set({permissions:[{key:'dashboard.read',organizations:dashboardScope},{key:'business.read',organizations:['org-synthetic']}]});
      const data = completeIndicators(); data.execution_summary.scope.organization_ids = dashboardScope;
      response.next(data); fixture.detectChanges();
      const link = fixture.nativeElement.querySelector('a[href*="/dashboard/related/workorders"]') as HTMLAnchorElement;
      expect(link.textContent).toContain('Ver Workorders autorizadas');
      expect(link.getAttribute('href')).toContain('view=current');
      expect(fixture.nativeElement.textContent).toContain('escopo de acesso mais restrito');
      expect(fixture.nativeElement.querySelectorAll('.indicator-value')[1].textContent).toBe('3');
    });
  }

  it('does not label a selected permitted organization as a narrower detail scope', () => {
    profile.set({permissions:[{key:'dashboard.read',organizations:['org-synthetic','org-b']},{key:'business.read',organizations:['org-synthetic']}]});
    params.next(convertToParamMap({organization_id:'org-synthetic'}));
    response.next(completeIndicators()); fixture.detectChanges();
    expect(fixture.componentInstance.workorderAccess()).toBe('same');
    expect(fixture.nativeElement.textContent).not.toContain('escopo de acesso mais restrito');
  });

  it('keeps authorized indicators visible but offers no forbidden detail link', () => {
    profile.set({permissions:[{key:'dashboard.read',organizations:['org-synthetic']}]});
    response.next(completeIndicators()); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('a[href*="/dashboard/related/workorders"]')).toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.indicator-value')[1].textContent).toBe('3');
    expect(fixture.nativeElement.textContent).toContain('não os detalhes deste recorte');
  });

});

function completeIndicators(): Indicators {
  return { generated_at: '2026-09-03T12:00:00Z', source: 'synergia.operational', organizations: [{ id: 'org-synthetic', code: 'syn-org', name: 'Organização sintética' }], filters: { organization_id: null, date_from: null, date_to: null }, executions: { completed: 2, failed: 1 }, execution_summary: executionAggregate({completed:2,failed:1},{scope:{permission:'dashboard.read',organization_ids:['org-synthetic']}}), workorders: { total: 4, partially_released: 1 }, workorders_current: { total: 3, partially_released: 1 }, quantities_coverage: completeQuantityCoverage(), pending_items: { open: 2 }, quantities: { planned: 20, produced: 15, received: 12, released: 10 } };
}

function failure(kind: ApiFailure['kind'], status: number): ApiFailure {
  return { kind, status, code: 'synthetic', message: 'synthetic', correlationId: null, fields: [] };
}
