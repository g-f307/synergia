import { Component, DestroyRef, ElementRef, HostListener, computed, effect, inject, signal, viewChild } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';

import { SessionService } from './core/session.service';
import { ThemeService } from './core/theme.service';
import { NotificationService } from './domains/notifications/notification.service';
import { BreadcrumbsComponent } from './layout/breadcrumbs.component';
import { I18nService } from './shared/i18n/i18n.service';
import { TranslationKey } from './shared/i18n/i18n.models';

interface NavigationItem { label: TranslationKey; route: string; permission: string; icon: string; implemented: boolean; }
type NavigationContext = Pick<NavigationItem, 'label' | 'icon'> & { detail?: string; detailKey?: TranslationKey; hideBreadcrumbs?: boolean };

@Component({ selector: 'app-root', imports: [RouterLink, RouterLinkActive, RouterOutlet, BreadcrumbsComponent], templateUrl: './app.component.html', styleUrl: './app.component.css' })
export class AppComponent {
  readonly title = 'SYNERGIA';
  readonly i18n = inject(I18nService);
  readonly session = inject(SessionService);
  readonly theme = inject(ThemeService);
  readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly menuButton = viewChild<ElementRef<HTMLButtonElement>>('menuButton');
  private readonly mobileQuery = window.matchMedia('(max-width: 48rem)');
  private readonly syncMobile = (event: MediaQueryListEvent): void => this.isMobile.set(event.matches);
  readonly menuOpen = signal(false);
  readonly isMobile = signal(this.mobileQuery.matches);
  readonly sidebarCollapsed = signal(localStorage.getItem('synergia.sidebar.collapsed') === 'true');
  readonly currentNavigation = signal<NavigationContext>({ label: 'navigation.dashboard', icon: 'dashboard.svg' });
  readonly items: NavigationItem[] = [
    { label: 'navigation.dashboard', route: '/dashboard', permission: 'dashboard.read', icon: 'dashboard.svg', implemented: true },
    { label: 'navigation.newImport', route: '/imports/new', permission: 'import.create', icon: 'spreadsheet.svg', implemented: true },
    { label: 'navigation.executions', route: '/executions', permission: 'execution.read', icon: 'run.svg', implemented: true },
    { label: 'navigation.search', route: '/search', permission: 'business.read', icon: 'search.svg', implemented: true },
    { label: 'navigation.pending', route: '/pending-items', permission: 'pending.read', icon: 'queue.svg', implemented: true },
    { label: 'navigation.reports', route: '/reports', permission: 'report.read', icon: 'report.svg', implemented: true }
  ];
  readonly visibleItems = computed(() => this.items.filter((item) => item.implemented && this.session.hasPermission(item.permission)));

  constructor() {
    effect(() => {
      if (this.session.isAuthenticated() && this.session.hasPermission('notification.read')) this.notifications.refreshUnreadCount();
      else this.notifications.reset();
    });
    this.mobileQuery.addEventListener('change', this.syncMobile);
    this.destroyRef.onDestroy(() => this.mobileQuery.removeEventListener('change', this.syncMobile));
    this.router.events.pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd)).subscribe((event) => {
      this.menuOpen.set(false);
      this.currentNavigation.set(this.navigationContextFor(event.urlAfterRedirects));
      if (this.session.isAuthenticated() && this.session.hasPermission('notification.read')) this.notifications.refreshUnreadCount();
      setTimeout(() => document.getElementById('main-content')?.focus({ preventScroll: true }));
    });
  }

  toggleMenu(): void { this.menuOpen.update((value) => !value); }
  toggleSidebar(): void {
    this.sidebarCollapsed.update((value) => !value);
    localStorage.setItem('synergia.sidebar.collapsed', String(this.sidebarCollapsed()));
  }
  toggleTheme(): void { this.theme.toggle(); }
  logout(): void { this.notifications.reset(); this.session.logout().subscribe(); }
  navigationDetail(): string | undefined {
    const context = this.currentNavigation();
    const section = context.detailKey ? this.i18n.t(context.detailKey) : undefined;
    return section && context.detail ? `${section} / ${context.detail}` : section || context.detail;
  }

  @HostListener('document:keydown.escape')
  closeMenu(): void {
    if (!this.menuOpen()) return;
    this.menuOpen.set(false);
    this.menuButton()?.nativeElement.focus();
  }

  private navigationContextFor(url: string): NavigationContext {
    const path = url.split('?')[0];
    if (path === '/dashboard/related/workorders') return { label: 'dashboard.workorders', icon: 'production.svg', hideBreadcrumbs: true };
    if (path.startsWith('/workorders/')) return { label: 'dashboard.workorders', icon: 'production.svg', detail: decodeURIComponent(path.slice('/workorders/'.length)), hideBreadcrumbs: true };
    if (path.startsWith('/pending-items/')) return { label: 'navigation.pending', icon: 'queue.svg', detail: decodeURIComponent(path.slice('/pending-items/'.length)), hideBreadcrumbs: true };
    if (path.startsWith('/imports/') && path !== '/imports/new') return { label: 'navigation.imports', icon: 'spreadsheet.svg', detail: decodeURIComponent(path.slice('/imports/'.length)), hideBreadcrumbs: true };
    if (path.startsWith('/lots/')) return { label: 'navigation.lots', icon: 'production.svg', detail: decodeURIComponent(path.slice('/lots/'.length)), hideBreadcrumbs: true };
    if (path.startsWith('/serials/')) return { label: 'navigation.serials', icon: 'production.svg', detail: decodeURIComponent(path.slice('/serials/'.length)), hideBreadcrumbs: true };
    if (path.startsWith('/reports/')) return { label: 'navigation.reports', icon: 'report.svg', detail: decodeURIComponent(path.slice('/reports/'.length)), hideBreadcrumbs: true };
    if (path === '/admin/users') return { label: 'navigation.admin', icon: 'shield.svg', detailKey: 'adminUi.users', hideBreadcrumbs: true };
    if (path === '/admin/roles') return { label: 'navigation.admin', icon: 'shield.svg', detailKey: 'adminUi.roles', hideBreadcrumbs: true };
    if (path === '/admin/groups') return { label: 'navigation.admin', icon: 'shield.svg', detailKey: 'adminUi.groups', hideBreadcrumbs: true };
    if (path === '/admin/users/new') return { label: 'navigation.admin', icon: 'shield.svg', detailKey: 'adminUi.users', hideBreadcrumbs: true };
    if (path === '/admin/roles/new') return { label: 'navigation.admin', icon: 'shield.svg', detailKey: 'adminUi.roles', hideBreadcrumbs: true };
    if (path === '/admin/groups/new') return { label: 'navigation.admin', icon: 'shield.svg', detailKey: 'adminUi.groups', hideBreadcrumbs: true };
    if (path.startsWith('/admin/users/')) return { label: 'navigation.admin', icon: 'shield.svg', detailKey: 'adminUi.users', detail: decodeURIComponent(path.slice('/admin/users/'.length)), hideBreadcrumbs: true };
    if (path.startsWith('/admin/roles/')) return { label: 'navigation.admin', icon: 'shield.svg', detailKey: 'adminUi.roles', detail: decodeURIComponent(path.slice('/admin/roles/'.length)), hideBreadcrumbs: true };
    if (path.startsWith('/admin/groups/')) return { label: 'navigation.admin', icon: 'shield.svg', detailKey: 'adminUi.groups', detail: decodeURIComponent(path.slice('/admin/groups/'.length)), hideBreadcrumbs: true };
    if (path === '/admin/notification-templates') return { label: 'navigation.admin', icon: 'shield.svg', detailKey: 'notificationAdmin.title', hideBreadcrumbs: true };
    if (path === '/admin/notification-templates/new') return { label: 'navigation.admin', icon: 'shield.svg', detailKey: 'notificationAdmin.newTitle', hideBreadcrumbs: true };
    if (path.startsWith('/admin/notification-templates/')) return { label: 'notificationAdmin.title', icon: 'shield.svg', detail: decodeURIComponent(path.slice('/admin/notification-templates/'.length)), hideBreadcrumbs: true };
    const item = this.items.find((candidate) => path === candidate.route || path.startsWith(`${candidate.route}/`));
    if (item) {
      const detail = item.route === '/executions' && path.startsWith('/executions/')
        ? decodeURIComponent(path.slice('/executions/'.length))
        : undefined;
      return { label: item.label, icon: item.icon, detail };
    }
    if (path.startsWith('/admin')) return { label: 'navigation.admin', icon: 'shield.svg' };
    if (path.startsWith('/notifications')) return { label: 'navigation.notifications', icon: 'notification.svg' };
    if (path.startsWith('/profile')) return { label: 'navigation.profile', icon: 'settings.svg' };
    return { label: 'navigation.dashboard', icon: 'dashboard.svg' };
  }
}
