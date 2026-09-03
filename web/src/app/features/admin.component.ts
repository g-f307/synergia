import { AsyncPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { catchError, forkJoin, of } from 'rxjs';

import { environment } from '../../environments/environment';
import { BadgeComponent, CardComponent, StateComponent } from '../shared/ui/ui-kit';
import { I18nService } from '../shared/i18n/i18n.service';

interface Page<T> { items: T[]; total: number; }
interface Named {
  id: string;
  display_name?: string;
  group_name?: string;
  role_key?: string;
  status?: string;
}

@Component({
  imports: [AsyncPipe, BadgeComponent, CardComponent, StateComponent],
  template: `
    <section aria-labelledby="admin-title">
      <p class="eyebrow">{{ i18n.t('admin.eyebrow') }}</p>
      <h1 id="admin-title">{{ i18n.t('admin.title') }}</h1>
      @if (resources$ | async; as resources) {
        <div class="grid">
          <article class="card"><h2>{{ i18n.t('admin.users', { count: i18n.formatNumber(resources.users.total) }) }}</h2>
            @for (item of resources.users.items; track item.id) {
              <p>{{ item.display_name }} — {{ userStatus(item.status) }}</p>
            }
          </article>
          <article class="card"><h2>{{ i18n.t('admin.groups', { count: i18n.formatNumber(resources.groups.total) }) }}</h2>
            @for (item of resources.groups.items; track item.id) {
              <p>{{ item.group_name }}</p>
            }
          </article>
          <article class="card"><h2>{{ i18n.t('admin.roles', { count: i18n.formatNumber(resources.roles.total) }) }}</h2>
            @for (item of resources.roles.items; track item.id) {
              <p>{{ item.role_key }}</p>
            }
          </article>
        </div>
      } @else {
        @if (forbidden()) {
          <p role="alert">{{ i18n.t('admin.forbidden') }}</p>
        } @else {
          <p role="status">{{ i18n.t(failed() ? 'admin.unavailable' : 'admin.loading') }}</p>
        }
      }
      <details class="card">
        <summary>{{ i18n.t('catalog.title') }}</summary>
        <p>{{ i18n.t('catalog.description') }}</p>
        <div class="grid" data-testid="visual-catalog">
          <syn-card><h2>{{ i18n.t('catalog.surface') }}</h2><p>{{ i18n.t('catalog.supportText') }}</p><div class="catalog-row"><syn-badge tone="success">{{ i18n.t('catalog.success') }}</syn-badge><syn-badge tone="partial">{{ i18n.t('state.partial.title') }}</syn-badge><syn-badge tone="error">{{ i18n.t('state.forbidden.title') }}</syn-badge></div><button>{{ i18n.t('common.confirm') }}</button> <button class="secondary">{{ i18n.t('common.cancel') }}</button></syn-card>
          <syn-state state="partial" [title]="i18n.t('state.partial.title')" [message]="i18n.t('state.partial.message')" />
          <syn-state state="forbidden" [title]="i18n.t('state.forbidden.title')" [message]="i18n.t('state.forbidden.message')" />
          <syn-state state="unavailable" [title]="i18n.t('state.unavailable.title')" [message]="i18n.t('state.unavailable.message')" />
        </div>
      </details>
    </section>`,
  styles: ['details{margin-top:var(--syn-space-6)}summary{cursor:pointer;font-weight:700}.catalog-row{display:flex;flex-wrap:wrap;gap:var(--syn-space-2);margin-bottom:var(--syn-space-4)}']
})
export class AdminComponent {
  readonly i18n = inject(I18nService);
  private readonly http = inject(HttpClient);
  readonly failed = signal(false);
  readonly forbidden = signal(false);
  readonly resources$ = forkJoin({
    users: this.http.get<Page<Named>>(`${environment.apiUrl}/admin/users`),
    groups: this.http.get<Page<Named>>(`${environment.apiUrl}/admin/access/groups`),
    roles: this.http.get<Page<Named>>(`${environment.apiUrl}/admin/access/roles`)
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
