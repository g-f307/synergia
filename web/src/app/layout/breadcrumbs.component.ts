import { Component, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter } from 'rxjs';

import { I18nService } from '../shared/i18n/i18n.service';
import { TranslationKey } from '../shared/i18n/i18n.models';

interface Crumb { label: TranslationKey | string; translated: boolean; route?: string; }

@Component({
  selector: 'syn-breadcrumbs',
  imports: [RouterLink],
  template: `<nav [attr.aria-label]="i18n.t('accessibility.breadcrumb')"><ol><li><a routerLink="/profile">{{ i18n.t('navigation.home') }}</a></li>@for (crumb of crumbs(); track crumb.label) {<li>@if (crumb.route) {<a [routerLink]="crumb.route">{{ label(crumb) }}</a>} @else {<span aria-current="page">{{ label(crumb) }}</span>}</li>}</ol></nav>`,
  styles: ['ol{display:flex;flex-wrap:wrap;gap:var(--syn-space-2);list-style:none;margin:0 0 var(--syn-space-5);padding:0}li{color:var(--syn-text-secondary);font-size:13px}a{color:inherit;text-decoration:none}a:hover{color:var(--syn-primary);text-decoration:underline}li+li::before{color:var(--syn-text-secondary);content:"›";margin-right:var(--syn-space-2)}']
})
export class BreadcrumbsComponent {
  readonly i18n = inject(I18nService);
  private readonly router = inject(Router);
  readonly crumbs = signal<Crumb[]>(this.fromUrl(this.router.url));
  constructor() { this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe((event) => this.crumbs.set(this.fromUrl(event.urlAfterRedirects))); }
  label(crumb: Crumb): string { return crumb.translated ? this.i18n.t(crumb.label as TranslationKey) : crumb.label; }
  private fromUrl(url: string): Crumb[] {
    const labels: Record<string, TranslationKey> = { profile: 'navigation.profile', admin: 'navigation.admin', dashboard: 'navigation.dashboard', imports: 'navigation.imports', executions: 'navigation.executions', search: 'navigation.search', workorders: 'navigation.workorders', lots: 'navigation.lots', serials: 'navigation.serials', 'pending-items': 'navigation.pending' };
    const parts = url.split('?')[0].split('/').filter(Boolean);
    return parts.map((part, index) => ({ label: labels[part] ?? part, translated: part in labels, route: index < parts.length - 1 ? `/${parts.slice(0, index + 1).join('/')}` : undefined }));
  }
}
