import { AsyncPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { catchError, forkJoin, of } from 'rxjs';

import { environment } from '../../environments/environment';

interface Page<T> { items: T[]; total: number; }
interface Named {
  id: string;
  display_name?: string;
  group_name?: string;
  role_key?: string;
  status?: string;
}

@Component({
  imports: [AsyncPipe],
  template: `
    <section aria-labelledby="admin-title">
      <p class="eyebrow">Acesso restrito</p>
      <h1 id="admin-title">Administração</h1>
      @if (resources$ | async; as resources) {
        <div class="grid">
          <article class="card"><h2>Usuários ({{ resources.users.total }})</h2>
            @for (item of resources.users.items; track item.id) {
              <p>{{ item.display_name }} — {{ item.status }}</p>
            }
          </article>
          <article class="card"><h2>Grupos ({{ resources.groups.total }})</h2>
            @for (item of resources.groups.items; track item.id) {
              <p>{{ item.group_name }}</p>
            }
          </article>
          <article class="card"><h2>Papéis ({{ resources.roles.total }})</h2>
            @for (item of resources.roles.items; track item.id) {
              <p>{{ item.role_key }}</p>
            }
          </article>
        </div>
      } @else {
        <p>{{ failed() ? 'Administração indisponível.' : 'Carregando recursos administrativos…' }}</p>
      }
    </section>`
})
export class AdminComponent {
  private readonly http = inject(HttpClient);
  readonly failed = signal(false);
  readonly resources$ = forkJoin({
    users: this.http.get<Page<Named>>(`${environment.apiUrl}/admin/users`),
    groups: this.http.get<Page<Named>>(`${environment.apiUrl}/admin/access/groups`),
    roles: this.http.get<Page<Named>>(`${environment.apiUrl}/admin/access/roles`)
  }).pipe(catchError(() => {
    this.failed.set(true);
    return of(null);
  }));
}
