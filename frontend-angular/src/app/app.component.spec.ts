import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { AppComponent } from './app.component';

describe('AppComponent', () => {
  let httpController: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpController = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpController.verify());

  it('should create the app', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it(`should have the 'SYNERGIA' title`, () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    expect(app.title).toEqual('SYNERGIA');
  });

  it('should render loading before the health request completes', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('.status--loading')?.textContent)
      .toContain('Verificando disponibilidade');
    httpController.expectOne('http://localhost:8000/health');
  });

  it('should render available when the health request succeeds', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    httpController.expectOne('http://localhost:8000/health')
      .flush({ status: 'ok', service: 'synergia-api' });
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('.status--ok')?.textContent)
      .toContain('API disponível: synergia-api');
  });

  it('should render unavailable when the health request fails', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    httpController.expectOne('http://localhost:8000/health')
      .flush('failure', { status: 503, statusText: 'Service Unavailable' });
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('.status--offline')?.textContent)
      .toContain('API indisponível');
  });
});
