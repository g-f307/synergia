import { AsyncPipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { catchError, forkJoin, of } from 'rxjs';

import { environment } from '../../environments/environment';
import { I18nService } from '../shared/i18n/i18n.service';
import { StateComponent } from '../shared/ui/ui-kit';

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
  imports: [AsyncPipe, RouterLink, StateComponent],
  template: `
    <section class="admin-page" aria-labelledby="admin-title">
      <header class="admin-heading">
        <div>
          <h1 id="admin-title">{{ i18n.t('admin.overviewTitle') }}</h1>
          <p>{{ i18n.t('admin.overviewDescription') }}</p>
        </div>
        <a class="primary-action" routerLink="/admin/users/new">
          <span aria-hidden="true">+</span>
          {{ i18n.t('adminUi.newUser') }}
        </a>
      </header>

      @if (resources$ | async; as resources) {
        <section class="admin-metrics" [attr.aria-label]="i18n.t('admin.summaryLabel')">
          <article><span>{{ i18n.t('adminUi.users') }}</span><strong class="metric-value">{{ i18n.formatNumber(resources.users.total) }}</strong></article>
          <article><span>{{ i18n.t('adminUi.groups') }}</span><strong class="metric-value">{{ i18n.formatNumber(resources.groups.total) }}</strong></article>
          <article><span>{{ i18n.t('adminUi.roles') }}</span><strong class="metric-value">{{ i18n.formatNumber(resources.roles.total) }}</strong></article>
          <article><span>{{ i18n.t('admin.permissions') }}</span><strong class="metric-value">{{ i18n.formatNumber(resources.permissions.length) }}</strong></article>
        </section>

        <section class="management" aria-labelledby="management-title">
          <div class="section-heading">
            <div>
              <h2 id="management-title">{{ i18n.t('admin.resourcesTitle') }}</h2>
              <p>{{ i18n.t('admin.resourcesDescription') }}</p>
            </div>
          </div>
          <nav class="management-grid" [attr.aria-label]="i18n.t('adminUi.navigation')">
            <a class="management-link" routerLink="/admin/users">
              <span class="management-icon"><img src="assets/icons/human-review.svg" alt="" width="22" height="22" /></span>
              <span class="management-copy"><strong>{{ i18n.t('adminUi.users') }}</strong><small>{{ i18n.t('admin.usersDescription') }}</small></span>
              <span class="management-total">{{ i18n.formatNumber(resources.users.total) }}</span><span class="management-arrow" aria-hidden="true">›</span>
            </a>
            <a class="management-link" routerLink="/admin/groups">
              <span class="management-icon"><img src="assets/icons/team.svg" alt="" width="22" height="22" /></span>
              <span class="management-copy"><strong>{{ i18n.t('adminUi.groups') }}</strong><small>{{ i18n.t('admin.groupsDescription') }}</small></span>
              <span class="management-total">{{ i18n.formatNumber(resources.groups.total) }}</span><span class="management-arrow" aria-hidden="true">›</span>
            </a>
            <a class="management-link" routerLink="/admin/roles">
              <span class="management-icon"><img src="assets/icons/role-badge.svg" alt="" width="22" height="22" /></span>
              <span class="management-copy"><strong>{{ i18n.t('adminUi.roles') }}</strong><small>{{ i18n.t('admin.rolesDescription') }}</small></span>
              <span class="management-total">{{ i18n.formatNumber(resources.roles.total) }}</span><span class="management-arrow" aria-hidden="true">›</span>
            </a>
            <a class="management-link" routerLink="/admin/notification-templates">
              <span class="management-icon"><img src="assets/icons/notification.svg" alt="" width="22" height="22" /></span>
              <span class="management-copy"><strong>{{ i18n.t('notificationAdmin.title') }}</strong><small>{{ i18n.t('admin.templatesDescription') }}</small></span>
              <span class="management-arrow" aria-hidden="true">›</span>
            </a>
          </nav>
        </section>

        <section class="recent-users" aria-labelledby="recent-users-title">
          <div class="section-heading">
            <div>
              <h2 id="recent-users-title">{{ i18n.t('admin.recentUsers') }}</h2>
              <p>{{ i18n.t('admin.recentUsersDescription') }}</p>
            </div>
            <a routerLink="/admin/users">{{ i18n.t('admin.viewAll') }} <span aria-hidden="true">→</span></a>
          </div>
          @if (resources.users.items.length) {
            <div class="user-list">
              @for (item of recentUsers(resources.users.items); track item.id) {
                <a class="user-row" [routerLink]="['/admin/users', item.id]">
                  <span class="user-avatar" aria-hidden="true">{{ userInitial(item.display_name) }}</span>
                  <span class="user-name">{{ item.display_name || item.id }}</span>
                  <span class="user-status" [attr.data-status]="userStatusTone(item.status)">{{ userStatus(item.status) }}</span>
                  <span class="user-arrow" aria-hidden="true">›</span>
                </a>
              }
            </div>
          } @else {
            <p class="empty-copy">{{ i18n.t('admin.noUsers') }}</p>
          }
        </section>
      } @else {
        <div class="admin-state">
          @if (forbidden()) {
            <syn-state state="forbidden" [title]="i18n.t('admin.forbiddenTitle')" [message]="i18n.t('admin.forbidden')" />
          } @else if (failed()) {
            <syn-state state="unavailable" [title]="i18n.t('admin.unavailableTitle')" [message]="i18n.t('admin.unavailable')" />
          } @else {
            <syn-state state="loading" [title]="i18n.t('admin.loadingTitle')" [message]="i18n.t('admin.loading')" />
          }
        </div>
      }
    </section>
  `,
  styleUrl: './admin.component.css'
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

  recentUsers(users: Named[]): Named[] { return users.slice(0, 4); }
  userInitial(name?: string): string { return name?.trim().charAt(0).toUpperCase() || '?'; }

  userStatus(status?: string): string {
    const statuses = { pending: 'userStatus.pending', active: 'userStatus.active', blocked: 'userStatus.blocked', inactive: 'userStatus.inactive' } as const;
    return this.i18n.t(statuses[status as keyof typeof statuses] ?? 'userStatus.unknown');
  }

  userStatusTone(status?: string): string {
    return ['pending', 'active', 'blocked', 'inactive'].includes(status ?? '') ? status! : 'unknown';
  }
}
