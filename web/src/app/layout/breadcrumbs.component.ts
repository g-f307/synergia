import { Component, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter } from 'rxjs';

interface Crumb { label: string; route?: string; }

@Component({
  selector: 'syn-breadcrumbs',
  imports: [RouterLink],
  template: `<nav aria-label="Breadcrumb"><ol><li><a routerLink="/profile">Início</a></li>@for (crumb of crumbs(); track crumb.label) {<li>@if (crumb.route) {<a [routerLink]="crumb.route">{{ crumb.label }}</a>} @else {<span aria-current="page">{{ crumb.label }}</span>}</li>}</ol></nav>`,
  styles: ['ol{display:flex;flex-wrap:wrap;gap:var(--space-2);list-style:none;margin:0 0 var(--space-4);padding:0}li+li::before{color:var(--color-muted);content:"/";margin-right:var(--space-2)}']
})
export class BreadcrumbsComponent {
  private readonly router = inject(Router);
  readonly crumbs = signal<Crumb[]>(this.fromUrl(this.router.url));
  constructor() { this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe((event) => this.crumbs.set(this.fromUrl(event.urlAfterRedirects))); }
  private fromUrl(url: string): Crumb[] {
    const labels: Record<string, string> = { profile: 'Perfil', admin: 'Administração', dashboard: 'Visão geral', imports: 'Importações', executions: 'Execuções', search: 'Consulta', workorders: 'Workorders', lots: 'Lotes', serials: 'Seriais', 'pending-items': 'Pendências' };
    const parts = url.split(/[/?]/).filter(Boolean);
    return parts.map((part, index) => ({ label: labels[part] ?? part, route: index < parts.length - 1 ? `/${parts.slice(0, index + 1).join('/')}` : undefined }));
  }
}
