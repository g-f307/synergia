import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { AppComponent } from './app.component';
import { SessionService } from './core/session.service';
import { NotificationService } from './domains/notifications/notification.service';

describe('AppComponent', () => {
  const authenticated = signal(false);
  const administrator = signal(false);
  const notificationPermission = signal(false);
  const profile = signal<{ display_name: string } | null>(null);
  const notifications = { unreadCount: signal(0), refreshUnreadCount: jasmine.createSpy(), reset: jasmine.createSpy() };
  const session = {
    isAuthenticated: authenticated,
    isAdministrator: administrator,
    profile,
    hasPermission: (key: string) => key === 'dashboard.read' || (key === 'notification.read' && notificationPermission()),
    logout: () => of(undefined)
  };

  beforeEach(async () => {
    document.documentElement.dataset['theme'] = 'light';
    authenticated.set(false);
    administrator.set(false);
    notificationPermission.set(false);
    notifications.unreadCount.set(0);
    profile.set(null);
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [
        provideRouter([]),
        { provide: SessionService, useValue: session },
        { provide: NotificationService, useValue: notifications }
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
    expect(element.querySelector('.brand')?.getAttribute('aria-label')).toContain('SYNERGIA');
    expect(element.querySelector('.topbar-context')).toBeNull();
    expect(element.textContent).toContain('Perfil');
    expect(element.textContent).toContain('Visão geral');
    expect(element.textContent).not.toContain('Administração');
  });

  it('updates the authenticated brand variant when the theme changes', () => {
    authenticated.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const logo = () => fixture.nativeElement.querySelector('.brand-full') as HTMLImageElement;
    expect(logo().getAttribute('src')).toBe('/assets/logos/logo-horizontal.png');

    fixture.componentInstance.toggleTheme();
    fixture.detectChanges();

    expect(logo().getAttribute('src')).toBe('/assets/logos/logo-negativa-horizontal.png');
    const compact = fixture.nativeElement.querySelector('.brand-compact') as HTMLImageElement;
    expect(compact.getAttribute('src')).toBe('/assets/logos/simbolo-negativo.png');
  });

  it('shows administration only with a global administrative permission', () => {
    authenticated.set(true);
    administrator.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Administração');
  });

  it('shows an accessible unread notification count with permission', () => {
    authenticated.set(true);
    notificationPermission.set(true);
    notifications.unreadCount.set(3);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const link = fixture.nativeElement.querySelector('.notification-button') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/notifications');
    expect(link.getAttribute('aria-label')).toContain('3 não lidas');
    expect(link.querySelector('.notification-badge')?.textContent).toContain('3');
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
