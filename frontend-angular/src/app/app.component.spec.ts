import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { AppComponent } from './app.component';
import { SessionService } from './core/session.service';

describe('AppComponent', () => {
  const authenticated = signal(false);
  const administrator = signal(false);
  const session = {
    isAuthenticated: authenticated,
    isAdministrator: administrator,
    logout: () => of(undefined)
  };

  beforeEach(async () => {
    authenticated.set(false);
    administrator.set(false);
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [
        provideRouter([]),
        { provide: SessionService, useValue: session }
      ]
    }).compileComponents();
  });

  it('creates the authenticated application shell', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;

    expect(fixture.componentInstance.title).toBe('SYNERGIA');
    expect(element.querySelector('.brand')?.textContent).toContain('SYNERGIA');
    expect(element.textContent).toContain('Meu perfil');
    expect(element.textContent).not.toContain('Administração');
  });

  it('shows administration only with a global administrative permission', () => {
    authenticated.set(true);
    administrator.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Administração');
  });
});
