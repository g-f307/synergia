import { Component, ElementRef, HostListener, computed, inject, signal, viewChild } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';

import { SessionService } from './core/session.service';
import { BreadcrumbsComponent } from './layout/breadcrumbs.component';
import { I18nService } from './shared/i18n/i18n.service';
import { TranslationKey } from './shared/i18n/i18n.models';

interface NavigationItem { label: TranslationKey; route: string; permission: string; icon: string; implemented: boolean; }

@Component({ selector: 'app-root', imports: [RouterLink, RouterLinkActive, RouterOutlet, BreadcrumbsComponent], templateUrl: './app.component.html', styleUrl: './app.component.css' })
export class AppComponent {
  readonly title = 'SYNERGIA';
  readonly i18n = inject(I18nService);
  readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly menuButton = viewChild<ElementRef<HTMLButtonElement>>('menuButton');
  readonly menuOpen = signal(false);
  readonly darkTheme = signal(false);
  readonly items: NavigationItem[] = [
    { label: 'navigation.dashboard', route: '/dashboard', permission: 'dashboard.read', icon: 'dashboard.svg', implemented: false },
    { label: 'navigation.newImport', route: '/imports/new', permission: 'import.create', icon: 'spreadsheet.svg', implemented: false },
    { label: 'navigation.search', route: '/search', permission: 'business.read', icon: 'search.svg', implemented: false },
    { label: 'navigation.pending', route: '/pending-items', permission: 'pending.read', icon: 'queue.svg', implemented: false }
  ];
  readonly visibleItems = computed(() => this.items.filter((item) => item.implemented && this.session.hasPermission(item.permission)));

  constructor() {
    this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe(() => {
      this.menuOpen.set(false);
      setTimeout(() => document.getElementById('main-content')?.focus());
    });
  }

  toggleMenu(): void { this.menuOpen.update((value) => !value); }
  toggleTheme(): void { this.darkTheme.update((value) => !value); document.documentElement.dataset['theme'] = this.darkTheme() ? 'dark' : 'light'; }
  logout(): void { this.session.logout().subscribe(); }

  @HostListener('document:keydown.escape')
  closeMenu(): void {
    if (!this.menuOpen()) return;
    this.menuOpen.set(false);
    this.menuButton()?.nativeElement.focus();
  }
}
