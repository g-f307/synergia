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
  const executionPermission = signal(false);
  const profile = signal<{ display_name: string } | null>(null);
  const notifications = { unreadCount: signal(0), refreshUnreadCount: jasmine.createSpy(), reset: jasmine.createSpy() };
  const session = {
    isAuthenticated: authenticated,
    isAdministrator: administrator,
    profile,
    hasPermission: (key: string) => key === 'dashboard.read'
      || (key === 'notification.read' && notificationPermission())
      || (key === 'execution.read' && executionPermission()),
    logout: () => of(undefined)
  };

  beforeEach(async () => {
    document.documentElement.dataset['theme'] = 'light';
    document.documentElement.dataset['fontScale'] = 'normal';
    authenticated.set(false);
    administrator.set(false);
    notificationPermission.set(false);
    executionPermission.set(false);
    notifications.unreadCount.set(0);
    profile.set(null);
    localStorage.removeItem('synergia.sidebar.collapsed');
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
    expect(element.querySelector('.topbar-context')?.textContent).toContain('Visão geral');
    expect(element.querySelector('.topbar-context img')?.getAttribute('src')).toContain('dashboard.svg');
    expect(element.textContent).toContain('Perfil');
    expect(element.textContent).toContain('Visão geral');
    expect(element.textContent).not.toContain('Administração');
  });

  it('uses the play symbol to identify executions in the sidebar', () => {
    authenticated.set(true);
    executionPermission.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const executionsLink = fixture.nativeElement.querySelector('a[href="/executions"]') as HTMLAnchorElement;
    expect(executionsLink.querySelector('img')?.getAttribute('src')).toBe('/assets/icons/run.svg');
  });

  it('offers TV Mode in the header only with execution access', () => {
    authenticated.set(true);
    executionPermission.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const link = fixture.nativeElement.querySelector('.tv-mode-button') as HTMLAnchorElement;
    expect(link).not.toBeNull();
    expect(link.getAttribute('href')).toBe('/tv');
    expect(link.getAttribute('aria-label')).toContain('Modo TV');

    executionPermission.set(false);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.tv-mode-button')).toBeNull();
  });

  it('removes the standard shell while the TV route owns the viewport', () => {
    authenticated.set(true);
    executionPermission.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    const component = fixture.componentInstance as unknown as { tvMode: { set: (value: boolean) => void } };
    component.tvMode.set(true);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.shell')).toBeNull();
    expect(fixture.nativeElement.querySelector('.tv-shell')).not.toBeNull();
  });

  it('adds the execution identifier to the executions context on a detail route', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    const context = (fixture.componentInstance as unknown as { navigationContextFor: (url: string) => { detail?: string } }).navigationContextFor('/executions/exec-001?tab=summary');

    expect(context.detail).toBe('exec-001');
  });

  it('identifies the Workorders drill-down in the global header', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    const context = (fixture.componentInstance as unknown as { navigationContextFor: (url: string) => { label: string; icon: string; hideBreadcrumbs?: boolean } })
      .navigationContextFor('/dashboard/related/workorders?organization=org-1');

    expect(context.label).toBe('dashboard.workorders');
    expect(context.icon).toBe('production.svg');
    expect(context.hideBreadcrumbs).toBeTrue();
  });

  it('does not duplicate breadcrumbs in the administrative catalogs', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    const component = fixture.componentInstance as unknown as {
      navigationContextFor: (url: string) => { label: string; detailKey?: string; hideBreadcrumbs?: boolean };
    };

    const routes = [
      ['/admin/users', 'adminUi.users'],
      ['/admin/roles', 'adminUi.roles'],
      ['/admin/groups', 'adminUi.groups'],
      ['/admin/notification-templates', 'notificationAdmin.title']
    ] as const;
    for (const [route, detailKey] of routes) {
      const context = component.navigationContextFor(route);
      expect(context.label).toBe('navigation.admin');
      expect(context.detailKey).toBe(detailKey);
      expect(context.hideBreadcrumbs).toBeTrue();
    }
  });

  it('uses one contextual trail for administrative creation routes', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    const component = fixture.componentInstance as unknown as {
      navigationContextFor: (url: string) => { label: string; detailKey?: string; detail?: string; hideBreadcrumbs?: boolean };
    };

    for (const [route, detailKey] of [
      ['/admin/users/new', 'adminUi.users'],
      ['/admin/roles/new', 'adminUi.roles'],
      ['/admin/groups/new', 'adminUi.groups']
    ] as const) {
      const context = component.navigationContextFor(route);
      expect(context.label).toBe('navigation.admin');
      expect(context.detailKey).toBe(detailKey);
      expect(context.detail).toBeUndefined();
      expect(context.hideBreadcrumbs).toBeTrue();
    }
  });

  it('identifies administrative detail routes without rendering a second breadcrumb', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    const component = fixture.componentInstance as unknown as {
      navigationContextFor: (url: string) => { label: string; detailKey?: string; detail?: string; hideBreadcrumbs?: boolean };
    };

    for (const [route, detailKey, identifier] of [
      ['/admin/users/user-123', 'adminUi.users', 'user-123'],
      ['/admin/roles/role-123', 'adminUi.roles', 'role-123'],
      ['/admin/groups/group-123', 'adminUi.groups', 'group-123']
    ] as const) {
      const context = component.navigationContextFor(route);
      expect(context.label).toBe('navigation.admin');
      expect(context.detailKey).toBe(detailKey);
      expect(context.detail).toBe(identifier);
      expect(context.hideBreadcrumbs).toBeTrue();
    }
  });

  it('uses a single contextual trail for template creation and version details', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    const component = fixture.componentInstance as unknown as {
      navigationContextFor: (url: string) => { label: string; detail?: string; detailKey?: string; hideBreadcrumbs?: boolean };
    };

    const creation = component.navigationContextFor('/admin/notification-templates/new');
    expect(creation.label).toBe('navigation.admin');
    expect(creation.detailKey).toBe('notificationAdmin.newTitle');
    expect(creation.hideBreadcrumbs).toBeTrue();

    const detail = component.navigationContextFor('/admin/notification-templates/template-123');
    expect(detail.label).toBe('notificationAdmin.title');
    expect(detail.detail).toBe('template-123');
    expect(detail.hideBreadcrumbs).toBeTrue();
  });

  it('adds one Workorder identifier to its detail context without breadcrumbs', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    const context = (fixture.componentInstance as unknown as { navigationContextFor: (url: string) => { label: string; detail?: string; hideBreadcrumbs?: boolean } })
      .navigationContextFor('/workorders/WO-001?from=%2Fdashboard%2Frelated%2Fworkorders');

    expect(context.label).toBe('dashboard.workorders');
    expect(context.detail).toBe('WO-001');
    expect(context.hideBreadcrumbs).toBeTrue();
  });

  it('adds one pending-item identifier to its context without breadcrumbs', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    const context = (fixture.componentInstance as unknown as { navigationContextFor: (url: string) => { label: string; detail?: string; hideBreadcrumbs?: boolean } })
      .navigationContextFor('/pending-items/17?from=%2Fpending-items%3Fpage%3D2');

    expect(context.label).toBe('navigation.pending');
    expect(context.detail).toBe('17');
    expect(context.hideBreadcrumbs).toBeTrue();
  });

  it('adds one report identifier to its context without breadcrumbs', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    const context = (fixture.componentInstance as unknown as { navigationContextFor: (url: string) => { label: string; detail?: string; hideBreadcrumbs?: boolean } })
      .navigationContextFor('/reports/7126c6a0-8497-4c2e-a081-29d72e09cf27?version=1');

    expect(context.label).toBe('navigation.reports');
    expect(context.detail).toBe('7126c6a0-8497-4c2e-a081-29d72e09cf27');
    expect(context.hideBreadcrumbs).toBeTrue();
  });

  it('adds one import execution identifier to its context without breadcrumbs', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    const context = (fixture.componentInstance as unknown as { navigationContextFor: (url: string) => { label: string; detail?: string; hideBreadcrumbs?: boolean } })
      .navigationContextFor('/imports/exec-001');

    expect(context.label).toBe('navigation.imports');
    expect(context.detail).toBe('exec-001');
    expect(context.hideBreadcrumbs).toBeTrue();
  });

  it('adds one lot identifier to its context without breadcrumbs', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    const context = (fixture.componentInstance as unknown as { navigationContextFor: (url: string) => { label: string; detail?: string; hideBreadcrumbs?: boolean } })
      .navigationContextFor('/lots/LOT-001?execution_id=exec-001');

    expect(context.label).toBe('navigation.lots');
    expect(context.detail).toBe('LOT-001');
    expect(context.hideBreadcrumbs).toBeTrue();
  });

  it('adds one serial identifier to the Seriais context without breadcrumbs', () => {
    authenticated.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    const context = (fixture.componentInstance as unknown as { navigationContextFor: (url: string) => { label: string; icon: string; detail?: string; hideBreadcrumbs?: boolean } })
      .navigationContextFor('/serials/SER-001?execution_id=exec-001');

    expect(context.label).toBe('navigation.serials');
    expect(context.icon).toBe('production.svg');
    expect(context.detail).toBe('SER-001');
    expect(context.hideBreadcrumbs).toBeTrue();
  });

  it('groups navigation and operator identity inside the sidebar frame', () => {
    authenticated.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const sidebar = element.querySelector('.sidebar');

    expect(sidebar?.querySelector('.sidebar-header .brand')).not.toBeNull();
    expect(sidebar?.querySelector('.sidebar-header .sidebar-collapse')).not.toBeNull();
    const collapse = sidebar?.querySelector('.sidebar-collapse') as HTMLButtonElement;
    expect(getComputedStyle(collapse).position).toBe('absolute');
    expect(getComputedStyle(collapse).bottom).toBe('90px');
    expect(sidebar?.querySelector('nav')).not.toBeNull();
    expect(sidebar?.querySelector('.sidebar-account')?.textContent).toContain('Pessoa Sintética');
    expect(element.querySelector('.main-wrapper')?.classList).toContain('workspace');
  });

  it('keeps the application frame fixed and delegates scrolling to the routed surface', () => {
    authenticated.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const shell = element.querySelector('.shell') as HTMLElement;
    const content = element.querySelector('.content') as HTMLElement;

    expect(getComputedStyle(shell).overflow).toBe('hidden');
    expect(getComputedStyle(content).overflowY).toBe('hidden');
  });

  it('keeps the global focus ring visible on the focused main region', () => {
    authenticated.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const content = fixture.nativeElement.querySelector('#main-content') as HTMLElement;

    content.focus();

    expect(document.activeElement).toBe(content);
    expect(getComputedStyle(content).outlineStyle).toBe('solid');
  });

  it('collapses the desktop sidebar and persists the preference', () => {
    authenticated.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const shell = fixture.nativeElement.querySelector('.shell') as HTMLElement;
    const button = fixture.nativeElement.querySelector('.sidebar-collapse') as HTMLButtonElement;

    button.click();
    fixture.detectChanges();

    expect(shell.classList).toContain('sidebar-collapsed');
    expect(localStorage.getItem('synergia.sidebar.collapsed')).toBe('true');
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(getComputedStyle(button).position).toBe('absolute');
    expect(getComputedStyle(button).bottom).toBe('90px');
  });

  it('increases the computed sidebar navigation size with the large preference', () => {
    authenticated.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const link = fixture.nativeElement.querySelector('.sidebar nav a') as HTMLAnchorElement;
    const normalSize = Number.parseFloat(getComputedStyle(link).fontSize);

    document.documentElement.dataset['fontScale'] = 'large';
    const largeSize = Number.parseFloat(getComputedStyle(link).fontSize);

    expect(largeSize).toBeGreaterThan(normalSize);
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

    expect(logo().getAttribute('src')).toBe('/assets/logos/logo-dark-horizontal.svg');
    const compact = fixture.nativeElement.querySelector('.brand-compact') as HTMLImageElement;
    expect(compact.getAttribute('src')).toBe('/assets/logos/logo-dark-horizontal.svg');
  });

  it('renders the three header actions with one visual contract', () => {
    authenticated.set(true);
    notificationPermission.set(true);
    profile.set({ display_name: 'Pessoa Sintética' });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const actions = fixture.nativeElement.querySelectorAll('.account .topbar-action');
    expect(actions.length).toBe(3);
    expect(fixture.nativeElement.querySelector('.logout-button img')?.getAttribute('src')).toContain('logout.svg');
    expect([...actions].every((action: Element) => getComputedStyle(action).width === getComputedStyle(action).height)).toBeTrue();
    const account = fixture.nativeElement.querySelector('.account') as HTMLElement;
    const topbar = fixture.nativeElement.querySelector('.topbar') as HTMLElement;
    expect(Math.abs(topbar.getBoundingClientRect().right - account.getBoundingClientRect().right)).toBeLessThan(50);
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
