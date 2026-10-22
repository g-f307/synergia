import { Location } from '@angular/common';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, UrlTree, convertToParamMap, provideRouter } from '@angular/router';
import { Subject } from 'rxjs';

import { Lot, Serial } from './query.models';
import { EntityDetailComponent } from './entity-detail.component';
import { QueryService } from './query.service';

describe('EntityDetailComponent', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('keeps search context while navigating from a lot to related details', async () => {
    const setup = await createComponent('lot');
    setup.lotResponse.next(lot());
    setup.fixture.detectChanges();

    expect(hasLink(setup.router, ['/workorders', 'WO-001'], 'exec-001')).toBeTrue();
    expect(hasLink(setup.router, ['/serials', 'SER-001'], 'exec-001')).toBeTrue();
    expect(hasLinkFrom(setup.router, ['/serials', 'SER-001'], '/lots/LOT-001?execution_id=exec-001')).toBeTrue();
    expect(hasLink(setup.router, ['/executions', 'exec-001'])).toBeTrue();
    setup.fixture.componentInstance.back();
    expect(setup.router.navigateByUrl).toHaveBeenCalledWith('/search?type=lot&query=LOT-001');
  });

  it('presents the lot in one consistent surface with internal scrolling', async () => {
    const setup = await createComponent('lot');
    setup.lotResponse.next(lot());
    setup.fixture.detectChanges();
    const page = setup.fixture.nativeElement.querySelector('.entity-detail') as HTMLElement;
    const body = setup.fixture.nativeElement.querySelector('.detail-scroll') as HTMLElement;
    expect(getComputedStyle(page).overflow).toBe('hidden');
    expect(getComputedStyle(body).overflowY).toBe('auto');
    expect(setup.fixture.nativeElement.querySelector('h1')?.textContent).toContain('Detalhes do lote');
    expect(setup.fixture.nativeElement.querySelectorAll('.card').length).toBe(0);
    expect(setup.fixture.nativeElement.querySelector('.eyebrow')).toBeNull();
    expect(setup.fixture.nativeElement.querySelector('.entity-icon')).toBeNull();
  });

  it('gives the lot identifier and relationships a clear visual hierarchy', async () => {
    const setup = await createComponent('lot');
    setup.lotResponse.next(lot());
    setup.fixture.detectChanges();

    const identifier = setup.fixture.nativeElement.querySelector('[data-testid="entity-identifier"]');
    const metadata = setup.fixture.nativeElement.querySelector('.metadata-strip');
    const related = setup.fixture.nativeElement.querySelector('.related-records');
    expect(identifier?.textContent).toContain('LOT-001');
    expect(metadata).not.toBeNull();
    expect(related?.querySelectorAll('a').length).toBe(1);
  });

  it('returns from a lot to the workorder that opened it', async () => {
    const from = '/workorders/WO-001?execution_id=exec-001';
    const setup = await createComponent('lot', from);
    setup.lotResponse.next(lot());
    setup.fixture.detectChanges();

    setup.fixture.componentInstance.back();
    expect(setup.router.navigateByUrl).toHaveBeenCalledWith(from);
  });

  it('keeps search context while navigating from a serial detail', async () => {
    const setup = await createComponent('serial');
    setup.serialResponse.next(serial());
    setup.fixture.detectChanges();

    expect(setup.fixture.nativeElement.textContent).toContain('SER-001');
    expect(hasLink(setup.router, ['/workorders', 'WO-001'], 'exec-001')).toBeTrue();
    expect(hasLink(setup.router, ['/executions', 'exec-001'])).toBeTrue();
    setup.fixture.componentInstance.back();
    expect(setup.router.navigateByUrl).toHaveBeenCalledWith('/search?type=serial&query=SER-001');
  });

  it('places the serial title below the back button', async () => {
    const serialSetup = await createComponent('serial');
    serialSetup.serialResponse.next(serial());
    serialSetup.fixture.detectChanges();
    const serialToolbar = serialSetup.fixture.nativeElement.querySelector('.detail-toolbar') as HTMLElement;

    expect(serialToolbar.classList).toContain('serial-toolbar');
    expect(getComputedStyle(serialToolbar).display).toBe('grid');
  });

  it('returns from a serial to the lot that opened it', async () => {
    const from = '/lots/LOT-001?execution_id=exec-001';
    const setup = await createComponent('serial', from);
    setup.serialResponse.next(serial());
    setup.fixture.detectChanges();

    setup.fixture.componentInstance.back();
    expect(setup.router.navigateByUrl).toHaveBeenCalledWith(from);
  });

  it('returns through the real browser history when a serial has no explicit origin', async () => {
    const setup = await createComponent('serial', null);
    setup.serialResponse.next(serial());
    setup.fixture.detectChanges();

    setup.fixture.componentInstance.back();

    expect(setup.location.back).toHaveBeenCalled();
    expect(setup.router.navigateByUrl).not.toHaveBeenCalled();
  });

  it('identifies an incomplete serial without interrupting the detail with an outdated-data banner', async () => {
    const setup = await createComponent('serial');
    setup.serialResponse.next({ ...serial(), container_number: null, updated_at: '2000-01-01T00:00:00Z' });
    setup.fixture.detectChanges();

    expect(setup.fixture.nativeElement.querySelector('[data-state="partial"]')).not.toBeNull();
    expect(setup.fixture.nativeElement.querySelector('[data-state="stale"]')).toBeNull();
    expect(setup.fixture.nativeElement.textContent).toContain('SER-001');
  });
});

async function createComponent(entityType: 'lot' | 'serial', returnPath?: string | null): Promise<{
  fixture: ComponentFixture<EntityDetailComponent>;
  router: jasmine.SpyObj<Router>;
  location: Location;
  lotResponse: Subject<Lot>;
  serialResponse: Subject<Serial>;
}> {
  const lotResponse = new Subject<Lot>();
  const serialResponse = new Subject<Serial>();
  const from = returnPath === undefined ? `/search?type=${entityType}&query=${entityType === 'lot' ? 'LOT-001' : 'SER-001'}` : returnPath;
  const router = jasmine.createSpyObj<Router>(
    'Router',
    ['navigateByUrl', 'createUrlTree', 'serializeUrl'],
    { events: new Subject(), url: `/${entityType}s/identifier` }
  );
  router.createUrlTree.and.returnValue({} as UrlTree);
  router.serializeUrl.and.returnValue('/synthetic-link');
  await TestBed.configureTestingModule({
    imports: [EntityDetailComponent],
    providers: [
      provideRouter([]),
      { provide: Router, useValue: router },
      {
        provide: ActivatedRoute,
        useValue: {
          snapshot: {
            data: { entityType },
            paramMap: convertToParamMap(entityType === 'lot' ? { lotNumber: 'LOT-001' } : { serialNumber: 'SER-001' }),
            queryParamMap: convertToParamMap(from === null ? { execution_id: 'exec-001' } : { from, execution_id: 'exec-001' })
          }
        }
      },
      { provide: QueryService, useValue: { lot: () => lotResponse.asObservable(), serial: () => serialResponse.asObservable() } }
    ]
  }).compileComponents();
  const fixture = TestBed.createComponent(EntityDetailComponent);
  const location = TestBed.inject(Location);
  spyOn(location, 'back');
  fixture.detectChanges();
  return { fixture, router, location, lotResponse, serialResponse };
}

function hasLink(router: jasmine.SpyObj<Router>, commands: unknown[], executionId?: string): boolean {
  return router.createUrlTree.calls.allArgs().some(([actualCommands, options]) => {
    return JSON.stringify(actualCommands) === JSON.stringify(commands)
      && (!executionId || options?.queryParams?.['execution_id'] === executionId);
  });
}

function hasLinkFrom(router: jasmine.SpyObj<Router>, commands: unknown[], from: string): boolean {
  return router.createUrlTree.calls.allArgs().some(([actualCommands, options]) => {
    return JSON.stringify(actualCommands) === JSON.stringify(commands) && options?.queryParams?.['from'] === from;
  });
}

function lot(): Lot {
  return { execution_id: 'exec-001', workorder_number: 'WO-001', lot_number: 'LOT-001', serials: ['SER-001'], updated_at: '2026-09-04T12:00:00Z' };
}

function serial(): Serial {
  return { execution_id: 'exec-001', workorder_number: 'WO-001', lot_number: 'LOT-001', serial_number: 'SER-001', container_number: 'CONT-001', updated_at: '2026-09-04T12:00:00Z' };
}
