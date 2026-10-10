import { AsyncPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { catchError, forkJoin, of } from 'rxjs';

import { environment } from '../../environments/environment';
import { BadgeComponent } from '../shared/ui/ui-kit';
import { I18nService } from '../shared/i18n/i18n.service';

interface Page<T> { items: T[]; total: number; }
interface Named {
  id: string;
  display_name?: string;
  group_name?: string;
  role_key?: string;
  status?: string;
}
interface PermissionNamed { id: string; permission_key: string; }

@Component({
  imports: [AsyncPipe, BadgeComponent, RouterLink],
  template: `
    <section class="admin-overview" aria-labelledby="admin-title">
      <p class="eyebrow">{{ i18n.t('admin.eyebrow') }}</p>
      <h1 id="admin-title">{{ i18n.t('admin.title') }}</h1>
      <nav class="admin-navigation admin-tabs" [attr.aria-label]="i18n.t('adminUi.navigation')">
        <a routerLink="/admin/users">{{ i18n.t('adminUi.users') }}</a>
        <a routerLink="/admin/groups">{{ i18n.t('adminUi.groups') }}</a>
        <a routerLink="/admin/roles">{{ i18n.t('adminUi.roles') }}</a>
        <a routerLink="/admin/notification-templates">{{ i18n.t('notificationAdmin.title') }}</a>
      </nav>
      @if (resources$ | async; as resources) {
        <p>{{ i18n.t('adminUi.permissionCatalogCount', { count: i18n.formatNumber(resources.permissions.length) }) }}</p>
        <div class="grid">
          <article class="card admin-domain-card domain-users"><div class="domain-heading"><img src="/assets/icons/settings.svg" alt="" aria-hidden="true"><h2>{{ i18n.t('admin.users', { count: i18n.formatNumber(resources.users.total) }) }}</h2></div>
            @for (item of resources.users.items; track item.id) {
              <p>{{ item.display_name }} — {{ userStatus(item.status) }}</p>
            }
          </article>
          <article class="card admin-domain-card domain-groups"><div class="domain-heading"><img src="/assets/icons/layers.svg" alt="" aria-hidden="true"><h2>{{ i18n.t('admin.groups', { count: i18n.formatNumber(resources.groups.total) }) }}</h2></div>
            @for (item of resources.groups.items; track item.id) {
              <p>{{ item.group_name }}</p>
            }
            <a class="admin-card-link" routerLink="/admin/groups">{{ i18n.t('adminUi.viewGroups') }}</a>
          </article>
          <article class="card admin-domain-card domain-roles"><div class="domain-heading"><img src="/assets/icons/shield.svg" alt="" aria-hidden="true"><h2>{{ i18n.t('admin.roles', { count: i18n.formatNumber(resources.roles.total) }) }}</h2></div>
            @for (item of resources.roles.items; track item.id) {
              <p>{{ item.role_key }}</p>
            }
            <a class="admin-card-link" routerLink="/admin/roles">Gerenciar papéis</a>
          </article>
          <article class="card admin-domain-card domain-templates"><div class="domain-heading"><img src="/assets/icons/notification.svg" alt="" aria-hidden="true"><h2>{{ i18n.t('notificationAdmin.title') }}</h2></div><p>{{ i18n.t('notificationAdmin.empty') }}</p><a class="admin-card-link" routerLink="/admin/notification-templates">{{ i18n.t('notificationAdmin.title') }} ›</a></article>
        </div>
      } @else {
        @if (forbidden()) {
          <p role="alert" data-testid="admin-forbidden">{{ i18n.t('admin.forbidden') }}</p>
        } @else {
          <p role="status">{{ i18n.t(failed() ? 'admin.unavailable' : 'admin.loading') }}</p>
        }
      }
      <details class="visual-catalog" open>
        <summary><span>{{ i18n.t("catalog.title") }}</span><small>{{ i18n.t("catalog.description") }}</small></summary>
        <div class="catalog-showcase" data-testid="visual-catalog">
          <article class="catalog-specimen surface-specimen"><header><img src="/assets/icons/report.svg" alt="" aria-hidden="true"><div><h2>{{ i18n.t("catalog.surface") }}</h2><p>{{ i18n.t("catalog.supportText") }}</p></div></header><div class="catalog-body"><p>{{ i18n.t("catalog.supportText") }}</p><div class="catalog-row"><syn-badge tone="success">{{ i18n.t("catalog.success") }}</syn-badge><syn-badge tone="partial">{{ i18n.t("state.partial.title") }}</syn-badge><syn-badge tone="error">{{ i18n.t("state.forbidden.title") }}</syn-badge></div><button type="button">{{ i18n.t("common.confirm") }}</button><button type="button" class="secondary">{{ i18n.t("common.cancel") }}</button></div></article>
          <article class="catalog-specimen state-specimen partial-specimen"><header><img src="/assets/icons/state-partial.svg" alt="" aria-hidden="true"><h2>{{ i18n.t("state.partial.title") }}</h2></header><div class="catalog-body"><p>{{ i18n.t("state.partial.message") }}</p><div class="catalog-callout"><img src="/assets/icons/state-info.svg" alt="" aria-hidden="true"><span>{{ i18n.t("catalog.supportText") }}</span></div></div></article>
          <article class="catalog-specimen state-specimen error-specimen"><header><img src="/assets/icons/state-error.svg" alt="" aria-hidden="true"><h2>{{ i18n.t("state.forbidden.title") }}</h2></header><div class="catalog-body"><p>{{ i18n.t("state.forbidden.message") }}</p><div class="catalog-callout"><img src="/assets/icons/state-error.svg" alt="" aria-hidden="true"><span>{{ i18n.t("admin.forbidden") }}</span></div></div></article>
          <article class="catalog-specimen state-specimen unavailable-specimen"><header><img src="/assets/icons/state-unavailable.svg" alt="" aria-hidden="true"><h2>{{ i18n.t("state.unavailable.title") }}</h2></header><div class="catalog-body"><p>{{ i18n.t("state.unavailable.message") }}</p><div class="catalog-callout"><img src="/assets/icons/state-info.svg" alt="" aria-hidden="true"><span>{{ i18n.t("admin.unavailable") }}</span></div></div></article>
        </div>
      </details>
    </section>`,
  styles: ['details{margin-top:var(--syn-space-6)}summary{cursor:pointer;font-weight:700}.catalog-row{display:flex;flex-wrap:wrap;gap:var(--syn-space-2);margin-bottom:var(--syn-space-4)}', '.admin-overview{max-width:1200px}.admin-tabs{background:var(--syn-bg-card);border:1px solid var(--syn-border);border-radius:var(--syn-radius);display:flex;gap:var(--syn-space-2);margin:var(--syn-space-4) 0;overflow:auto;padding:var(--syn-space-2)}.admin-tabs a{border-radius:var(--syn-radius-sm);color:var(--syn-text);display:inline-flex;font-size:.8125rem;font-weight:700;padding:10px 14px;text-decoration:none;white-space:nowrap}.admin-tabs a:hover{background:var(--syn-primary-light);color:var(--syn-primary)}.admin-overview .grid{grid-template-columns:repeat(4,minmax(0,1fr))}.admin-domain-card{display:flex;flex-direction:column;min-height:210px}.domain-heading{align-items:center;display:flex;gap:var(--syn-space-2)}.domain-heading img{background:var(--syn-primary-light);border-radius:50%;height:36px;padding:9px;width:36px}.domain-groups img{background:var(--syn-info-bg)}.domain-roles img{background:var(--syn-success-bg)}.domain-templates img{background:var(--syn-partial-bg)}.domain-heading h2{border:0!important;margin:0!important;padding:0!important}.admin-domain-card p{color:var(--syn-text-secondary);font-size:.8125rem}.admin-card-link{border-top:1px solid var(--syn-border);color:var(--syn-primary);font-size:.8125rem;font-weight:700;margin-top:auto;padding-top:var(--syn-space-3);text-decoration:none}.admin-card-link:hover{text-decoration:underline}@media(max-width:1100px){.admin-overview .grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:767px){.admin-overview .grid{grid-template-columns:1fr}}', '.visual-catalog{margin-top:var(--syn-space-6)}.visual-catalog summary{cursor:pointer;list-style:none}.visual-catalog summary::-webkit-details-marker{display:none}.visual-catalog summary span{display:block;font-family:LGEIHeadline,LGEIText,sans-serif;font-size:1.25rem;font-weight:600}.visual-catalog summary small{color:var(--syn-text-secondary);display:block;margin-top:var(--syn-space-1)}.catalog-showcase{display:grid;gap:var(--syn-space-4);grid-template-columns:repeat(4,minmax(0,1fr));margin-top:var(--syn-space-5)}.catalog-specimen{background:var(--syn-bg-card);border:1px solid var(--syn-border);border-radius:var(--syn-radius-lg);box-shadow:var(--syn-shadow);overflow:hidden}.catalog-specimen header{align-items:center;border-bottom:1px solid var(--syn-border);display:flex;gap:var(--syn-space-3);padding:var(--syn-space-4)}.catalog-specimen header>img{background:var(--syn-bg);border-radius:50%;height:44px;padding:11px;width:44px}.catalog-specimen h2{font-size:1rem;margin:0}.catalog-specimen header p{color:var(--syn-text-secondary);font-size:.8125rem;margin:var(--syn-space-1) 0 0}.catalog-body{display:grid;gap:var(--syn-space-3);padding:var(--syn-space-4)}.catalog-body>p{color:var(--syn-text-secondary);font-size:.875rem;margin:0;min-height:4.5em}.catalog-row{gap:var(--syn-space-2);margin:0}.catalog-body button{width:100%}.catalog-callout{align-items:center;background:var(--syn-bg);border-radius:var(--syn-radius);display:flex;gap:var(--syn-space-2);font-size:.8125rem;padding:var(--syn-space-3)}.catalog-callout img{height:20px;width:20px}.partial-specimen{border-left:5px solid var(--syn-partial)}.partial-specimen header{background:var(--syn-partial-bg)}.error-specimen{border-left:5px solid var(--syn-error)}.error-specimen header{background:var(--syn-error-bg)}.unavailable-specimen{border-left:5px solid var(--syn-unavailable)}.unavailable-specimen header{background:var(--syn-unavailable-bg)}@media(max-width:1100px){.catalog-showcase{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:767px){.catalog-showcase{grid-template-columns:1fr}.catalog-body>p{min-height:0}}']
})
export class AdminComponent {
  readonly i18n = inject(I18nService);
  private readonly http = inject(HttpClient);
  readonly failed = signal(false);
  readonly forbidden = signal(false);
  readonly resources$ = forkJoin({
    users: this.http.get<Page<Named>>(`${environment.apiUrl}/admin/users`),
    groups: this.http.get<Page<Named>>(`${environment.apiUrl}/admin/access/groups`),
    roles: this.http.get<Page<Named>>(`${environment.apiUrl}/admin/access/roles`),
    permissions: this.http.get<PermissionNamed[]>(`${environment.apiUrl}/admin/access/permissions`)
  }).pipe(catchError((error: HttpErrorResponse) => {
    if (error.status === 403) this.forbidden.set(true);
    else this.failed.set(true);
    return of(null);
  }));

  userStatus(status?: string): string {
    const statuses = {
      pending: 'userStatus.pending',
      active: 'userStatus.active',
      blocked: 'userStatus.blocked',
      inactive: 'userStatus.inactive'
    } as const;
    return this.i18n.t(statuses[status as keyof typeof statuses] ?? 'userStatus.unknown');
  }
}
