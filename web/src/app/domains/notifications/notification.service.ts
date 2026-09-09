import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, of, tap } from 'rxjs';

import { environment } from '../../../environments/environment';
import { NotificationFilter, NotificationItem, NotificationPage, NotificationSort } from './notification.models';

@Injectable({ providedIn: 'root' })
export class NotificationService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/notifications`;
  private countGeneration = 0;
  readonly unreadCount = signal(0);

  list(filter: NotificationFilter, sort: NotificationSort, page: number, pageSize: number): Observable<NotificationPage> {
    const params = new HttpParams().set('filter', filter).set('sort', sort).set('page', page).set('page_size', pageSize);
    return this.http.get<NotificationPage>(this.base, { params });
  }

  refreshUnreadCount(): void {
    const generation = this.countGeneration;
    this.http.get<{ count: number }>(`${this.base}/unread-count`).pipe(
      catchError(() => of({ count: this.unreadCount() }))
    ).subscribe((response) => {
      if (generation === this.countGeneration) this.unreadCount.set(response.count);
    });
  }

  markRead(item: NotificationItem): Observable<NotificationItem> {
    return this.http.patch<NotificationItem>(`${this.base}/${encodeURIComponent(item.id)}/read`, { version: item.version }).pipe(
      tap(() => this.unreadCount.update((count) => Math.max(0, count - 1)))
    );
  }

  markAllRead(): Observable<{ count: number }> {
    return this.http.post<{ count: number }>(`${this.base}/read-all`, {}).pipe(
      tap(() => this.unreadCount.set(0))
    );
  }

  reset(): void { this.countGeneration += 1; this.unreadCount.set(0); }
}
