import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { Indicators } from '../../shared/api/operational.models';
import { DashboardComponent } from './dashboard.component';
import { DashboardService } from './dashboard.service';

describe('DashboardComponent', () => {
  let fixture: ComponentFixture<DashboardComponent>;
  let response: Subject<Indicators>;
  let requestedFilters: unknown[];
  const profile = signal<{ permissions: Array<{ key: string; organizations: string[] | null }> }>({ permissions: [{ key: 'dashboard.read', organizations: ['org-synthetic'] }] });

  beforeEach(async () => {
    profile.set({ permissions: [{ key: 'dashboard.read', organizations: ['org-synthetic'] }] });
    response = new Subject<Indicators>();
    requestedFilters = [];
    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideRouter([]),
        { provide: DashboardService, useValue: { getIndicators: (filters: unknown) => { requestedFilters.push(filters); return response.asObservable(); } } },
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

    expect(text).toContain('Visão geral operacional');
    expect(text).toContain('synergia.operational');
    expect(text).toContain('Liberações parciais: 1');
    expect(text).toContain('Planejada');
    expect(fixture.nativeElement.querySelectorAll('.indicator-card').length).toBe(3);
    expect(fixture.nativeElement.querySelector('syn-state')).toBeNull();
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

    expect(fixture.nativeElement.textContent).toContain('Resultado parcial');
    expect(fixture.nativeElement.textContent).toContain('Ausente');
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

  it('describes global scope without relying on color', () => {
    profile.set({ permissions: [{ key: 'dashboard.read', organizations: null }] });
    response.next(completeIndicators());
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Escopo global autorizado');
    expect(fixture.nativeElement.querySelector('[aria-labelledby="dashboard-title"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelectorAll('label').length).toBe(3);
  });

  it('applies filters and preserves them in related navigation', async () => {
    response.next(completeIndicators());
    fixture.componentInstance.organizationId.set('org-synthetic');
    fixture.componentInstance.dateFrom.set('2026-08-01');
    fixture.componentInstance.dateTo.set('2026-08-31');
    fixture.componentInstance.applyFilters(new Event('submit'));
    await fixture.whenStable();
    response.next(completeIndicators());
    fixture.detectChanges();

    expect(requestedFilters.at(-1)).toEqual({ organizationId: 'org-synthetic', dateFrom: '2026-08-01', dateTo: '2026-08-31' });
    const href = (fixture.nativeElement.querySelector('.indicator-card a') as HTMLAnchorElement).getAttribute('href') ?? '';
    expect(href).toContain('organization=org-synthetic');
    expect(href).toContain('dateFrom=2026-08-01');
  });

  it('rejects an inverted period before requesting data', () => {
    fixture.componentInstance.dateFrom.set('2026-09-01');
    fixture.componentInstance.dateTo.set('2026-08-01');
    fixture.componentInstance.applyFilters(new Event('submit'));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).toContain('data inicial');
    expect(requestedFilters.length).toBe(1);
  });
});

function completeIndicators(): Indicators {
  return { generated_at: '2026-09-03T12:00:00Z', source: 'synergia.operational', organizations: [{ id: 'org-synthetic', code: 'syn-org', name: 'Organização sintética' }], filters: { organization_id: null, date_from: null, date_to: null }, executions: { completed: 2, failed: 1 }, workorders: { total: 4, partially_released: 1 }, pending_items: { open: 2 }, quantities: { planned: 20, produced: 15, received: 12, released: 10 } };
}

function failure(kind: ApiFailure['kind'], status: number): ApiFailure {
  return { kind, status, code: 'synthetic', message: 'synthetic', correlationId: null, fields: [] };
}
