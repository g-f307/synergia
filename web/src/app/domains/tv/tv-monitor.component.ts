import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { Subscription } from 'rxjs';

import { ThemeService } from '../../core/theme.service';
import { I18nService } from '../../shared/i18n/i18n.service';
import { ApiFailure } from '../../shared/api/api-error';
import { EXECUTION_OUTCOMES, ExecutionCatalogItem, ExecutionFrame, ExecutionScopeFilters } from '../executions/execution.models';
import { ExecutionService } from '../executions/execution.service';
import { ExecutionScopeComponent } from '../executions/execution-scope.component';
import { executionUrlParams, filtersFromAggregate, filtersFromParams, outcomeLabel } from '../executions/execution-presentation';

type TvPanel = 'executions' | 'sources';
type TvState = 'loading' | 'ready' | 'stale' | 'error' | 'forbidden';

interface SourceSummary {
  name: string;
  executions: number;
  rowsRead: number;
  latestAt: string;
  attention: number;
  executionShare: number;
  attentionShare: number;
}

@Component({
  selector: 'app-tv-monitor',
  imports: [ExecutionScopeComponent],
  templateUrl: './tv-monitor.component.html',
  styleUrl: './tv-monitor.component.css'
})
export class TvMonitorComponent implements OnInit, OnDestroy {
  readonly i18n = inject(I18nService);
  readonly theme = inject(ThemeService);
  private readonly executions = inject(ExecutionService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private request?: Subscription;
  private routeRequest?: Subscription;
  private requested: ExecutionScopeFilters = {};
  private requestKey = '';
  private invalidRoute = false;
  private refreshTimer?: number;
  private clockTimer?: number;
  private carouselTimer?: number;
  private readonly reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  readonly frame = signal<ExecutionFrame | null>(null);
  readonly result = computed(() => this.frame()?.page ?? null);
  readonly aggregate = computed(() => this.frame()?.summary ?? null);
  readonly outcomes = EXECUTION_OUTCOMES;
  readonly state = signal<TvState>('loading');
  readonly activePanel = signal<TvPanel>('executions');
  readonly carouselCycle = signal(0);
  readonly refreshing = signal(false);
  readonly now = signal(new Date());
  readonly recent = computed(() => this.result()?.items.slice(0, 6) ?? []);
  readonly counts = computed(() => this.aggregate()?.by_outcome);
  readonly sourceSummaries = computed<SourceSummary[]>(() => {
    const total = this.aggregate()?.total ?? 0;
    return (this.aggregate()?.by_source ?? []).map(source => ({
      name: source.source ?? this.i18n.t('executions.scope.noSource'),
      executions: source.total, rowsRead: source.rows_read, latestAt: source.latest_started_at,
      attention: source.by_outcome.failed + source.by_outcome.partial,
      executionShare: total ? Math.round(source.total / total * 100) : 0,
      attentionShare: source.total ? Math.round((source.by_outcome.failed + source.by_outcome.partial) / source.total * 100) : 0
    })).sort((left, right) => right.attention - left.attention || right.executions - left.executions || left.name.localeCompare(right.name));
  });

  ngOnInit(): void {
    this.routeRequest = this.route.queryParamMap.subscribe(params => {
      try {
        const filters = filtersFromParams(params, this.i18n.timezone());
        this.invalidRoute = false;
        const key = JSON.stringify(executionUrlParams(filters));
        if (key === this.requestKey) return;
        this.requested = filters; this.load();
      } catch { this.invalidRoute = true; this.requestKey = ''; this.request?.unsubscribe(); this.state.set(this.frame() ? 'stale' : 'error'); this.refreshing.set(false); }
    });
    this.refreshTimer = window.setInterval(() => this.load(), 30_000);
    this.clockTimer = window.setInterval(() => this.now.set(new Date()), 1_000);
    this.startCarousel();
    document.addEventListener('visibilitychange', this.handleVisibility);
    this.reduceMotion.addEventListener('change', this.handleMotionPreference);
  }

  ngOnDestroy(): void {
    this.request?.unsubscribe();
    this.routeRequest?.unsubscribe();
    if (this.refreshTimer) window.clearInterval(this.refreshTimer);
    if (this.clockTimer) window.clearInterval(this.clockTimer);
    this.stopCarousel();
    document.removeEventListener('visibilitychange', this.handleVisibility);
    this.reduceMotion.removeEventListener('change', this.handleMotionPreference);
  }

  load(): void {
    if (this.invalidRoute) return;
    this.request?.unsubscribe();
    this.refreshing.set(true);
    if (!this.result()) this.state.set('loading');
    this.requestKey = JSON.stringify(executionUrlParams(this.requested));
    this.request = this.executions.frame({ ...this.requested, page: 1, pageSize: 25, sort: 'newest' }).subscribe({
      next: (result) => {
        this.frame.set(result);
        this.requested = filtersFromAggregate(result.summary);
        this.requestKey = JSON.stringify(executionUrlParams(this.requested));
        if (!this.router.getCurrentNavigation()) void this.router.navigate([], { relativeTo: this.route, queryParams: executionUrlParams(this.requested), replaceUrl: true });
        this.state.set('ready');
        this.refreshing.set(false);
      },
      error: (failure: ApiFailure) => {
        if (failure.kind === 'forbidden' || failure.kind === 'unauthorized' || failure.status === 403 || failure.status === 401) {
          this.frame.set(null);
          this.state.set('forbidden');
        } else {
          this.state.set(this.result() ? 'stale' : 'error');
        }
        this.refreshing.set(false);
      }
    });
  }

  selectPanel(panel: TvPanel): void {
    this.activePanel.set(panel);
    this.startCarousel();
  }

  toggleTheme(): void { this.theme.toggle(); }

  async requestFullscreen(): Promise<void> {
    if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
      await document.documentElement.requestFullscreen();
    }
  }

  async sendFeedback(): Promise<void> {
    if (document.fullscreenElement && document.exitFullscreen) await document.exitFullscreen();
    await this.router.navigate(['/feedback/new'], { queryParams: { source: 'tv' } });
  }
  async exit(): Promise<void> {
    if (document.fullscreenElement && document.exitFullscreen) await document.exitFullscreen();
    await this.router.navigate(['/dashboard'], { queryParams: executionUrlParams(this.aggregate() ? filtersFromAggregate(this.aggregate()!) : this.requested) });
  }

  statusLabel(item: ExecutionCatalogItem): string {
    return this.label(item.outcome);
  }
  label(value: string): string { return this.i18n.t(outcomeLabel(value)); }

  clockLabel(): string {
    return new Intl.DateTimeFormat(this.i18n.locale(), {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      timeZone: this.i18n.timezone()
    }).format(this.now());
  }

  private readonly handleVisibility = (): void => {
    if (document.hidden) this.stopCarousel();
    else this.startCarousel();
  };

  private readonly handleMotionPreference = (event: MediaQueryListEvent): void => {
    if (event.matches) this.stopCarousel();
    else this.startCarousel();
  };

  private startCarousel(): void {
    this.stopCarousel();
    this.carouselCycle.update((cycle) => cycle + 1);
    if (this.reduceMotion.matches || document.hidden) return;
    this.carouselTimer = window.setInterval(() => {
      this.activePanel.update((panel) => panel === 'executions' ? 'sources' : 'executions');
      this.carouselCycle.update((cycle) => cycle + 1);
    }, 15_000);
  }

  private stopCarousel(): void {
    if (this.carouselTimer) window.clearInterval(this.carouselTimer);
    this.carouselTimer = undefined;
  }
}
