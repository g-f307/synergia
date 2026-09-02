import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { AppComponent } from './app.component';
import { SessionService } from './core/session.service';

describe('AppComponent', () => {
  const authenticated = signal(false);
  const administrator = signal(false);
  const profile = signal<{ display_name: string } | null>(null);
  const session = {
    isAuthenticated: authenticated,
    isAdministrator: administrator,
    profile,
    hasPermission: (key: string) => key === 'dashboard.read',
    logout: () => of(undefined)
  };

  beforeEach(async () => {
    authenticated.set(false);
    administrator.set(false);
    profile.set(null);
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
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;

    expect(fixture.componentInstance.title).toBe('SYNERGIA');
    expect(element.querySelector('.brand img')?.getAttribute('alt')).toBe('SYNERGIA');
    expect(element.textContent).toContain('Perfil');
    expect(element.textContent).not.toContain('Visão geral');
    expect(element.textContent).not.toContain('Administração');
  });

  it('shows administration only with a global administrative permission', () => {
    authenticated.set(true);
    administrator.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Administração');
  });

  it('removes closed mobile navigation from focus and restores it when opened', () => {
    spyOn(window, 'matchMedia').and.returnValue({
      matches: true,
      addEventListener: jasmine.createSpy('addEventListener'),
      removeEventListener: jasmine.createSpy('removeEventListener')
    } as unknown as MediaQueryList);
    authenticated.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const button = fixture.nativeElement.querySelector('.menu-button') as HTMLButtonElement;
    button.style.display = 'inline-grid';
    const sidebar = fixture.nativeElement.querySelector('.sidebar') as HTMLElement;
    const link = sidebar.querySelector('a') as HTMLAnchorElement;

    expect(sidebar.hasAttribute('inert')).toBeTrue();
    link.focus();
    expect(document.activeElement).not.toBe(link);

    button.focus();
    button.click();
    fixture.detectChanges();
    expect(sidebar.hasAttribute('inert')).toBeFalse();
    link.focus();
    expect(document.activeElement).toBe(link);

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    fixture.detectChanges();

    expect(fixture.componentInstance.menuOpen()).toBeFalse();
    expect(sidebar.hasAttribute('inert')).toBeTrue();
    expect(document.activeElement).toBe(button);
  });
});
