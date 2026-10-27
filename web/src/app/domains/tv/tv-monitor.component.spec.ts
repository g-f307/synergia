import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { Subject } from 'rxjs';

import { ExecutionCatalogPage } from '../executions/execution.models';
import { ExecutionService } from '../executions/execution.service';
import { ApiFailure } from '../../shared/api/api-error';
import { TvMonitorComponent } from './tv-monitor.component';

describe('TvMonitorComponent', () => {
  let fixture: ComponentFixture<TvMonitorComponent> | undefined;
  let response: Subject<ExecutionCatalogPage>;
  let currentResponse: Subject<ExecutionCatalogPage>;

  beforeEach(async () => {
    response = new Subject<ExecutionCatalogPage>();
    currentResponse = response;
    await TestBed.configureTestingModule({
      imports: [TvMonitorComponent],
      providers: [
        provideRouter([]),
        { provide: ExecutionService, useValue: { list: () => currentResponse.asObservable() } }
      ]
    }).compileComponents();
  });

  afterEach(() => fixture?.destroy());

  it('turns the latest authorized executions into a distance-readable monitor', () => {
    createFixture();
    response.next(executionPage());
    fixture!.detectChanges();
    const element = fixture!.nativeElement as HTMLElement;

    expect(element.querySelector('.tv-monitor')).not.toBeNull();
    expect(element.querySelector<HTMLImageElement>('.tv-brand img')?.getAttribute('src')).toBe(
      '/assets/logos/logo-negativa-horizontal.png'
    );
    expect(element.querySelector('.tv-brand')?.textContent).toContain('Monitor de execuções');
    expect([...element.querySelectorAll('.tv-kpi strong')].map((node) => node.textContent?.trim())).toEqual(['1', '1', '1', '1']);
    expect(element.querySelector('.tv-execution-table')?.textContent).toContain('exec-active');
    expect(element.querySelector('.tv-execution-table')?.textContent).toContain('N-FP');
    expect(element.querySelector('.tv-execution-table')?.textContent).toContain('1.200');
    expect(element.querySelector('[aria-live="polite"]')?.textContent).toContain('Atualizado');
  });

  it('aggregates observed sources without claiming source availability', () => {
    createFixture();
    response.next(executionPage());
    fixture!.detectChanges();
    const sourceButton = fixture!.nativeElement.querySelector('[data-panel-target="sources"]') as HTMLButtonElement;

    sourceButton.click();
    fixture!.detectChanges();

    const panel = fixture!.nativeElement.querySelector('[data-panel="sources"]') as HTMLElement;
    expect(sourceButton.getAttribute('aria-pressed')).toBe('true');
    expect(panel.hidden).toBeFalse();
    expect(panel.querySelector('.tv-panel-heading')?.getAttribute('data-alignment')).toBe('start');
    expect(panel.querySelector('.tv-panel-heading > strong')).toBeNull();
    expect(panel.querySelector('.tv-source-grid')?.getAttribute('data-layout')).toBe('comparison');
    expect(panel.textContent).toContain('N-FP');
    expect(panel.textContent).toContain('2 execuções observadas');
    const nfpCard = [...panel.querySelectorAll<HTMLElement>('.tv-source-card')]
      .find((card) => card.querySelector('h3')?.textContent?.trim() === 'N-FP');
    expect(nfpCard?.getAttribute('data-density')).toBe('display');
    expect((nfpCard?.querySelector('.tv-volume-bar span') as HTMLElement).style.width).toBe('67%');
    expect(nfpCard?.querySelector('.tv-attention-ring')?.textContent).toContain('0 de 2');
    expect(panel.textContent).not.toContain('Disponível');
  });

  it('shows the active page and advances its timed progress indicator', fakeAsync(() => {
    createFixture();
    response.next(executionPage());
    fixture!.detectChanges();

    const progress = fixture!.nativeElement.querySelector('.tv-page-progress') as HTMLElement;
    expect(progress.querySelectorAll('.tv-page-segment').length).toBe(2);
    expect(progress.querySelector('.tv-page-segment.is-active')?.getAttribute('data-progress-panel')).toBe('executions');
    expect(progress.querySelector('.tv-page-fill')).not.toBeNull();

    tick(15_000);
    fixture!.detectChanges();

    expect(progress.querySelector('.tv-page-segment.is-active')?.getAttribute('data-progress-panel')).toBe('sources');
  }));

  it('refreshes automatically and replaces the displayed snapshot', fakeAsync(() => {
    createFixture();
    response.next(executionPage());
    fixture!.detectChanges();
    const next = new Subject<ExecutionCatalogPage>();
    currentResponse = next;

    tick(30_000);
    next.next(executionPage('exec-refreshed'));
    fixture!.detectChanges();

    expect(fixture!.nativeElement.textContent).toContain('exec-refreshed');
    expect(fixture!.nativeElement.textContent).not.toContain('exec-active');
  }));

  it('keeps the last snapshot visible when a later refresh fails', () => {
    createFixture();
    response.next(executionPage());
    fixture!.detectChanges();
    const next = new Subject<ExecutionCatalogPage>();
    currentResponse = next;
    const refresh = fixture!.nativeElement.querySelector('.tv-refresh') as HTMLButtonElement;

    refresh.click();
    next.error(new Error('offline'));
    fixture!.detectChanges();

    expect(fixture!.nativeElement.textContent).toContain('exec-active');
    expect(fixture!.nativeElement.querySelector('[role="status"]')?.textContent).toContain('desatualizados');
    expect(refresh.disabled).toBeFalse();
  });

  it('removes the previous snapshot when a refresh is forbidden', () => {
    createFixture();
    response.next(executionPage());
    fixture!.detectChanges();
    const next = new Subject<ExecutionCatalogPage>();
    currentResponse = next;
    const forbidden: ApiFailure = {
      kind: 'forbidden', status: 403, code: 'access_denied', message: 'safe', correlationId: null, fields: []
    };

    (fixture!.nativeElement.querySelector('.tv-refresh') as HTMLButtonElement).click();
    next.error(forbidden);
    fixture!.detectChanges();

    expect(fixture!.componentInstance.result()).toBeNull();
    expect(fixture!.nativeElement.textContent).not.toContain('exec-active');
    expect(fixture!.nativeElement.querySelector('[role="alert"]')?.textContent).toContain('Acesso negado');
  });

  it('stops rotating immediately when reduced motion is enabled and removes the listener', fakeAsync(() => {
    let changeListener: ((event: MediaQueryListEvent) => void) | undefined;
    const media = {
      matches: false,
      addEventListener: jasmine.createSpy('addEventListener').and.callFake((_type: string, listener: EventListener) => {
        changeListener = listener as (event: MediaQueryListEvent) => void;
      }),
      removeEventListener: jasmine.createSpy('removeEventListener')
    } as unknown as MediaQueryList;
    spyOn(window, 'matchMedia').and.returnValue(media);

    createFixture();
    expect(media.addEventListener).toHaveBeenCalledWith('change', jasmine.any(Function));
    changeListener?.({ matches: true } as MediaQueryListEvent);
    tick(15_000);

    expect(fixture!.componentInstance.activePanel()).toBe('executions');
    fixture!.destroy();
    fixture = undefined;
    expect(media.removeEventListener).toHaveBeenCalledWith('change', jasmine.any(Function));
  }));

  it('leaves the shell as the only main landmark', () => {
    createFixture();
    response.next(executionPage());
    fixture!.detectChanges();

    expect(fixture!.nativeElement.querySelector('main')).toBeNull();
    expect(fixture!.nativeElement.querySelector('.tv-stage')).not.toBeNull();
  });

  it('returns to the dashboard through an explicit accessible exit', () => {
    createFixture();
    response.next(executionPage());
    fixture!.detectChanges();
    const router = TestBed.inject(Router);
    const navigate = spyOn(router, 'navigateByUrl').and.resolveTo(true);
    const exit = fixture!.nativeElement.querySelector('.tv-exit') as HTMLButtonElement;

    exit.click();

    expect(exit.getAttribute('aria-label')).toContain('Sair');
    expect(navigate).toHaveBeenCalledWith('/dashboard');
  });

  function createFixture(): void {
    fixture = TestBed.createComponent(TvMonitorComponent);
    fixture.detectChanges();
  }
});

function executionPage(firstId = 'exec-active'): ExecutionCatalogPage {
  return {
    generated_at: '2026-10-27T03:00:00Z',
    items: [
      item(firstId, 'active', 'N-FP', 1200, '2026-10-27T02:59:00Z'),
      item('exec-completed', 'completed', 'N-FP', 800, '2026-10-27T02:50:00Z'),
      item('exec-partial', 'partial', 'WO Status', 500, '2026-10-27T02:40:00Z'),
      item('exec-failed', 'failed', null, 0, '2026-10-27T02:30:00Z')
    ],
    pagination: { page: 1, page_size: 25, total: 4, pages: 1 },
    sort: 'newest'
  };
}

function item(
  executionId: string,
  lifecycle: 'active' | 'completed' | 'partial' | 'failed',
  source: string | null,
  rowsRead: number,
  startedAt: string
) {
  return {
    execution_id: executionId,
    organization_id: 'org-synthetic',
    status: lifecycle === 'active' ? 'validating' : lifecycle,
    lifecycle,
    attempt: 1,
    source,
    file_types: ['xlsx'],
    file_count: 1,
    rows_read: rowsRead,
    error_count: lifecycle === 'failed' ? 1 : 0,
    warning_count: lifecycle === 'partial' ? 1 : 0,
    started_at: startedAt,
    finished_at: lifecycle === 'active' ? null : '2026-10-27T03:00:00Z'
  };
}
