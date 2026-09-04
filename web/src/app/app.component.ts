import { Component, DestroyRef, ElementRef, HostListener, computed, inject, signal, viewChild } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';

import { SessionService } from './core/session.service';
import { ThemeService } from './core/theme.service';
import { BreadcrumbsComponent } from './layout/breadcrumbs.component';
import { I18nService } from './shared/i18n/i18n.service';
import { TranslationKey } from './shared/i18n/i18n.models';

interface NavigationItem { label: TranslationKey; route: string; permission: string; icon: string; implemented: boolean; }

@Component({ selector: 'app-root', imports: [RouterLink, RouterLinkActive, RouterOutlet, BreadcrumbsComponent], templateUrl: './app.component.html', styleUrl: './app.component.css' })
export class AppComponent {
  readonly title = 'SYNERGIA';
  readonly i18n = inject(I18nService);
  readonly session = inject(SessionService);
  readonly theme = inject(ThemeService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly menuButton = viewChild<ElementRef<HTMLButtonElement>>('menuButton');
  private readonly mobileQuery = window.matchMedia('(max-width: 48rem)');
  private readonly syncMobile = (event: MediaQueryListEvent): void => this.isMobile.set(event.matches);
  readonly menuOpen = signal(false);
  readonly isMobile = signal(this.mobileQuery.matches);
  readonly items: NavigationItem[] = [
    { label: 'navigation.dashboard', route: '/dashboard', permission: 'dashboard.read', icon: 'dashboard.svg', implemented: true },
    { label: 'navigation.newImport', route: '/imports/new', permission: 'import.create', icon: 'spreadsheet.svg', implemented: true },
    { label: 'navigation.executions', route: '/executions', permission: 'execution.read', icon: 'dashboard.svg', implemented: true },
    { label: 'navigation.search', route: '/search', permission: 'business.read', icon: 'search.svg', implemented: false },
    { label: 'navigation.pending', route: '/pending-items', permission: 'pending.read', icon: 'queue.svg', implemented: false }
  ];
  readonly visibleItems = computed(() => this.items.filter((item) => item.implemented && this.session.hasPermission(item.permission)));

  constructor() {
    this.mobileQuery.addEventListener('change', this.syncMobile);
    this.destroyRef.onDestroy(() => this.mobileQuery.removeEventListener('change', this.syncMobile));
    this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe(() => {
      this.menuOpen.set(false);
      setTimeout(() => document.getElementById('main-content')?.focus({ preventScroll: true }));
    });
  }

  toggleMenu(): void { this.menuOpen.update((value) => !value); }
  toggleTheme(): void { this.theme.toggle(); }
  logout(): void { this.session.logout().subscribe(); }

  @HostListener('document:keydown.escape')
  closeMenu(): void {
    if (!this.menuOpen()) return;
    this.menuOpen.set(false);
    this.menuButton()?.nativeElement.focus();
  }
}
