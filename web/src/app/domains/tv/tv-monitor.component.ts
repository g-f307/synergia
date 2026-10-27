import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';

import { ThemeService } from '../../core/theme.service';
import { I18nService } from '../../shared/i18n/i18n.service';
import { ExecutionCatalogItem, ExecutionCatalogPage } from '../executions/execution.models';
import { ExecutionService } from '../executions/execution.service';

type TvPanel = 'executions' | 'sources';
type TvState = 'loading' | 'ready' | 'stale' | 'error';

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
  templateUrl: './tv-monitor.component.html',
  styleUrl: './tv-monitor.component.css'
})
export class TvMonitorComponent implements OnInit, OnDestroy {
  readonly i18n = inject(I18nService);
  readonly theme = inject(ThemeService);
  private readonly executions = inject(ExecutionService);
  private readonly router = inject(Router);
  private request?: Subscription;
  private refreshTimer?: number;
  private clockTimer?: number;
  private carouselTimer?: number;
  private readonly reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  readonly result = signal<ExecutionCatalogPage | null>(null);
  readonly state = signal<TvState>('loading');
  readonly activePanel = signal<TvPanel>('executions');
  readonly refreshing = signal(false);
  readonly now = signal(new Date());
  readonly recent = computed(() => this.result()?.items.slice(0, 6) ?? []);
  readonly counts = computed(() => {
    const totals = { active: 0, completed: 0, partial: 0, failed: 0 };
    for (const item of this.result()?.items ?? []) totals[item.lifecycle] += 1;
    return totals;
  });
  readonly sourceSummaries = computed<SourceSummary[]>(() => {
    const grouped = new Map<string, SourceSummary>();
    for (const item of this.result()?.items ?? []) {
      if (!item.source) continue;
      const current = grouped.get(item.source) ?? {
        name: item.source,
        executions: 0,
        rowsRead: 0,
        latestAt: item.started_at,
        attention: 0,
        executionShare: 0,
        attentionShare: 0
      };
      current.executions += 1;
      current.rowsRead += item.rows_read;
      current.attention += item.lifecycle === 'failed' || item.lifecycle === 'partial' ? 1 : 0;
      if (new Date(item.started_at) > new Date(current.latestAt)) current.latestAt = item.started_at;
      grouped.set(item.source, current);
    }
    const summaries = [...grouped.values()].sort((left, right) =>
      right.attention - left.attention || right.executions - left.executions || left.name.localeCompare(right.name)
    );
    const total = summaries.reduce((sum, source) => sum + source.executions, 0);
    return summaries.map((source) => ({
      ...source,
      executionShare: total ? Math.round(source.executions / total * 100) : 0,
      attentionShare: source.executions ? Math.round(source.attention / source.executions * 100) : 0
    }));
  });

  ngOnInit(): void {
    this.load();
    this.refreshTimer = window.setInterval(() => this.load(), 30_000);
    this.clockTimer = window.setInterval(() => this.now.set(new Date()), 1_000);
    this.startCarousel();
    document.addEventListener('visibilitychange', this.handleVisibility);
  }

  ngOnDestroy(): void {
    this.request?.unsubscribe();
    if (this.refreshTimer) window.clearInterval(this.refreshTimer);
    if (this.clockTimer) window.clearInterval(this.clockTimer);
    this.stopCarousel();
    document.removeEventListener('visibilitychange', this.handleVisibility);
  }

  load(): void {
    this.request?.unsubscribe();
    this.refreshing.set(true);
    if (!this.result()) this.state.set('loading');
    this.request = this.executions.list({ page: 1, pageSize: 25, sort: 'newest' }).subscribe({
      next: (result) => {
        this.result.set(result);
        this.state.set('ready');
        this.refreshing.set(false);
      },
      error: () => {
        this.state.set(this.result() ? 'stale' : 'error');
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

  async exit(): Promise<void> {
    if (document.fullscreenElement && document.exitFullscreen) await document.exitFullscreen();
    await this.router.navigateByUrl('/dashboard');
  }

  statusLabel(item: ExecutionCatalogItem): string {
    return this.i18n.t(`executions.lifecycle.${item.lifecycle}` as never);
  }

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

  private startCarousel(): void {
    this.stopCarousel();
    if (this.reduceMotion.matches || document.hidden) return;
    this.carouselTimer = window.setInterval(() => {
      this.activePanel.update((panel) => panel === 'executions' ? 'sources' : 'executions');
    }, 15_000);
  }

  private stopCarousel(): void {
    if (this.carouselTimer) window.clearInterval(this.carouselTimer);
    this.carouselTimer = undefined;
  }
}
