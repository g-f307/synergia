import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { SessionService } from './core/session.service';
import { BreadcrumbsComponent } from './layout/breadcrumbs.component';

interface NavigationItem { label: string; route: string; permission: string; icon: string; }

@Component({ selector: 'app-root', imports: [RouterLink, RouterLinkActive, RouterOutlet, BreadcrumbsComponent], templateUrl: './app.component.html', styleUrl: './app.component.css' })
export class AppComponent {
  readonly title = 'SYNERGIA';
  readonly session = inject(SessionService);
  readonly menuOpen = signal(false);
  readonly darkTheme = signal(false);
  readonly items: NavigationItem[] = [
    { label: 'Visão geral', route: '/dashboard', permission: 'dashboard.read', icon: 'dashboard.svg' },
    { label: 'Nova importação', route: '/imports/new', permission: 'import.create', icon: 'spreadsheet.svg' },
    { label: 'Consulta', route: '/search', permission: 'business.read', icon: 'search.svg' },
    { label: 'Pendências', route: '/pending-items', permission: 'pending.read', icon: 'queue.svg' }
  ];
  readonly visibleItems = computed(() => this.items.filter((item) => this.session.hasPermission(item.permission)));
  toggleMenu(): void { this.menuOpen.update((value) => !value); }
  toggleTheme(): void { this.darkTheme.update((value) => !value); document.documentElement.dataset['theme'] = this.darkTheme() ? 'dark' : 'light'; }
  logout(): void { this.session.logout().subscribe(); }
}
