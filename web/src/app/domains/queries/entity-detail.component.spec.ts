import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { ActivatedRoute, Router, RouterLink, UrlTree, convertToParamMap, provideRouter } from '@angular/router';
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

    expect(hasLink(setup.fixture, ['/workorders', 'WO-001'], 'exec-001')).toBeTrue();
    expect(hasLink(setup.fixture, ['/serials', 'SER-001'], 'exec-001')).toBeTrue();
    expect(hasLink(setup.fixture, ['/executions', 'exec-001'])).toBeTrue();
    setup.fixture.componentInstance.back();
    expect(setup.router.navigateByUrl).toHaveBeenCalledWith('/search?type=lot&query=LOT-001');
  });

  it('keeps search context while navigating from a serial detail', async () => {
    const setup = await createComponent('serial');
    setup.serialResponse.next(serial());
    setup.fixture.detectChanges();

    expect(setup.fixture.nativeElement.textContent).toContain('SER-001');
    expect(hasLink(setup.fixture, ['/workorders', 'WO-001'], 'exec-001')).toBeTrue();
    expect(hasLink(setup.fixture, ['/executions', 'exec-001'])).toBeTrue();
    setup.fixture.componentInstance.back();
    expect(setup.router.navigateByUrl).toHaveBeenCalledWith('/search?type=serial&query=SER-001');
  });
});

async function createComponent(entityType: 'lot' | 'serial'): Promise<{
  fixture: ComponentFixture<EntityDetailComponent>;
  router: jasmine.SpyObj<Router>;
  lotResponse: Subject<Lot>;
  serialResponse: Subject<Serial>;
}> {
  const lotResponse = new Subject<Lot>();
  const serialResponse = new Subject<Serial>();
  const from = `/search?type=${entityType}&query=${entityType === 'lot' ? 'LOT-001' : 'SER-001'}`;
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
            queryParamMap: convertToParamMap({ from, execution_id: 'exec-001' })
          }
        }
      },
      { provide: QueryService, useValue: { lot: () => lotResponse.asObservable(), serial: () => serialResponse.asObservable() } }
    ]
  }).compileComponents();
  const fixture = TestBed.createComponent(EntityDetailComponent);
  fixture.detectChanges();
  return { fixture, router, lotResponse, serialResponse };
}

function hasLink(fixture: ComponentFixture<EntityDetailComponent>, commands: unknown[], executionId?: string): boolean {
  return fixture.debugElement.queryAll(By.directive(RouterLink)).some((element) => {
    const link = element.injector.get(RouterLink);
    return JSON.stringify(link.routerLink) === JSON.stringify(commands)
      && (!executionId || link.queryParams?.['execution_id'] === executionId);
  });
}

function lot(): Lot {
  return { execution_id: 'exec-001', workorder_number: 'WO-001', lot_number: 'LOT-001', serials: ['SER-001'], updated_at: '2026-09-04T12:00:00Z' };
}

function serial(): Serial {
  return { execution_id: 'exec-001', workorder_number: 'WO-001', lot_number: 'LOT-001', serial_number: 'SER-001', container_number: 'CONT-001', updated_at: '2026-09-04T12:00:00Z' };
}
