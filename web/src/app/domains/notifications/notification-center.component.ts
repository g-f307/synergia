import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, ParamMap, Router } from '@angular/router';
import { Subject, catchError, combineLatest, map, of, startWith, switchMap, tap } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { PaginationComponent, StateComponent, UiState } from '../../shared/ui/ui-kit';
import { NotificationFilter, NotificationItem, NotificationPage, NotificationSort } from './notification.models';
import { NotificationService } from './notification.service';

@Component({
  selector: 'syn-notification-center',
  imports: [PaginationComponent, StateComponent],
  templateUrl: './notification-center.component.html',
  styleUrl: './notification-center.component.css'
})
export class NotificationCenterComponent {
  readonly i18n = inject(I18nService);
  private readonly api = inject(NotificationService);
  readonly unreadCount = this.api.unreadCount;
  private readonly route = inject(ActivatedRoute);
  readonly router = inject(Router);
  private readonly refreshRequested = new Subject<void>();
  readonly filter = signal<NotificationFilter>('all');
  readonly sort = signal<NotificationSort>('newest');
  readonly pageSize = signal(20);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly result = signal<NotificationPage | null>(null);
  readonly failure = signal<ApiFailure | null>(null);

  constructor() {
    combineLatest([this.route.queryParamMap, this.refreshRequested.pipe(startWith(undefined))]).pipe(
      tap(([params]) => { this.readParams(params); this.loading.set(true); this.failure.set(null); }),
      switchMap(([params]) => this.api.list(this.filter(), this.sort(), this.positive(params.get('page'), 1), this.pageSize()).pipe(
        map((value) => ({ value, failure: null })),
        catchError((failure: ApiFailure) => of({ value: null, failure }))
      )), takeUntilDestroyed()
    ).subscribe(({ value, failure }) => {
      this.result.set(value); this.failure.set(failure); this.loading.set(false);
      if (value) this.api.refreshUnreadCount();
    });
  }

  apply(event: Event): void { event.preventDefault(); this.navigate(1); }
  changePage(page: number): void { this.navigate(page); }
  refresh(): void { this.refreshRequested.next(); }
  markRead(item: NotificationItem): void {
    if (item.state === 'read' || this.busy()) return;
    this.busy.set(true);
    this.api.markRead(item).subscribe({
      next: (updated) => { this.busy.set(false); this.result.update((page) => page ? { ...page, items: page.items.map((entry) => entry.id === updated.id ? updated : entry) } : page); },
      error: (failure: ApiFailure) => { this.busy.set(false); this.failure.set(failure); }
    });
  }
  markAllRead(): void {
    if (this.busy() || this.unreadCount() === 0) return;
    this.busy.set(true);
    this.api.markAllRead().subscribe({
      next: () => { this.busy.set(false); this.refresh(); },
      error: (failure: ApiFailure) => { this.busy.set(false); this.failure.set(failure); }
    });
  }
  state(): UiState | null {
    const failure = this.failure();
    if (!failure || failure.kind === 'unauthorized') return null;
    if (failure.kind === 'forbidden') return 'forbidden';
    if (failure.kind === 'unavailable') return 'unavailable';
    return 'error';
  }
  failureTitle(): string { return this.i18n.t(this.failure()?.kind === 'forbidden' ? 'notifications.forbiddenTitle' : this.failure()?.kind === 'unavailable' ? 'notifications.unavailableTitle' : 'notifications.errorTitle'); }
  failureMessage(): string { return this.i18n.t(this.failure()?.kind === 'forbidden' ? 'notifications.forbidden' : this.failure()?.kind === 'unavailable' ? 'notifications.unavailable' : 'notifications.error'); }
  private readParams(params: ParamMap): void {
    const filter = params.get('filter'); const sort = params.get('sort');
    this.filter.set(filter === 'unread' || filter === 'read' ? filter : 'all');
    this.sort.set(sort === 'oldest' ? 'oldest' : 'newest');
    this.pageSize.set(this.positive(params.get('pageSize'), 20, [10, 20, 50]));
  }
  private navigate(page: number): void { void this.router.navigate([], { relativeTo: this.route, queryParams: { filter: this.filter(), sort: this.sort(), page, pageSize: this.pageSize() } }); }
  private positive(value: string | null, fallback: number, allowed?: number[]): number { const parsed = Number(value); return Number.isInteger(parsed) && parsed > 0 && (!allowed || allowed.includes(parsed)) ? parsed : fallback; }
}
