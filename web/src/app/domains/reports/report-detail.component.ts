import { Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, ParamMap, Router, RouterLink } from '@angular/router';
import { catchError, forkJoin, map, of, switchMap, tap } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { BadgeComponent, ModalComponent, PaginationComponent, ResponsiveTableComponent, StateComponent, UiState } from '../../shared/ui/ui-kit';
import { PENDING_PRIORITY_KEYS } from '../pending/pending-labels';
import { REPORT_COMPLETENESS_KEYS, REPORT_DATA_STATE_KEYS, REPORT_STATE_KEYS, REPORT_TYPE_KEYS } from './report-labels';
import { OqcReportData, OqcReportRow, ReportCompleteness, ReportDetail, ReportExportFormat, ReportPage, ReportPolicy, ReportState, ReportType, ReportVersion, WorkorderReportData, WorkorderReportRow } from './report.models';
import { ReportService } from './report.service';

type ReportTab = 'summary' | 'data' | 'history';

@Component({
  selector: 'syn-report-detail',
  imports: [BadgeComponent, ModalComponent, PaginationComponent, ResponsiveTableComponent, RouterLink, StateComponent],
  templateUrl: './report-detail.component.html',
  styleUrl: './report-detail.component.css'
})
export class ReportDetailComponent {
  readonly i18n = inject(I18nService);
  readonly session = inject(SessionService);
  readonly router = inject(Router);
  private readonly api = inject(ReportService);
  private readonly route = inject(ActivatedRoute);
  readonly reportId = this.route.snapshot.paramMap.get('reportId') ?? '';
  readonly loading = signal(true);
  readonly report = signal<ReportDetail | null>(null);
  readonly failure = signal<ApiFailure | null>(null);
  readonly history = signal<ReportPage | null>(null);
  readonly historyFailure = signal<ApiFailure | null>(null);
  readonly policy = signal<ReportPolicy | null>(null);
  readonly policyFailure = signal<ApiFailure | null>(null);
  readonly tab = signal<ReportTab>('summary');
  readonly rowPage = signal(1);
  readonly pageSize = signal(25);
  readonly historyPage = signal(1);
  readonly selectedFormat = signal<ReportExportFormat>('csv');
  readonly exporting = signal(false);
  readonly exportFailure = signal<ApiFailure | null>(null);
  readonly cancelOpen = signal(false);
  readonly cancelReason = signal('');
  readonly cancelBusy = signal(false);
  readonly cancelFailure = signal<ApiFailure | null>(null);
  readonly failureState = computed<UiState | null>(() => this.toState(this.failure()));
  readonly rows = computed<Array<WorkorderReportRow | OqcReportRow>>(() => {
    const data = this.report()?.data;
    if (!data) return [];
    return data.kind === 'workorder_consolidated' ? data.workorders : data.items;
  });
  readonly pagedRows = computed(() => this.rows().slice((this.rowPage() - 1) * this.pageSize(), this.rowPage() * this.pageSize()));
  readonly rowPages = computed(() => Math.ceil(this.rows().length / this.pageSize()));
  readonly returnUrl = computed(() => this.safeReturnUrl(this.route.snapshot.queryParamMap.get('from')));
  readonly canExport = computed(() => this.session.hasPermission('report.export') && this.report()?.state === 'succeeded' && (this.policy()?.export_formats.includes(this.selectedFormat()) ?? false));
  readonly canCancel = computed(() => this.session.hasPermission('report.cancel') && this.report()?.state === 'generating');
  readonly isStale = computed(() => { const item = this.report(); return !!item && item.state === 'generating' && Date.now() - Date.parse(item.created_at) > (this.policy()?.stale_after_seconds ?? 900) * 1000; });

  constructor() {
    this.api.policy().pipe(takeUntilDestroyed()).subscribe({
      next: (value) => { this.policy.set(value); this.policyFailure.set(null); if (!value.export_formats.includes(this.selectedFormat())) this.selectedFormat.set(value.export_formats[0] ?? 'csv'); },
      error: (failure: ApiFailure) => this.policyFailure.set(failure)
    });
    this.route.queryParamMap.pipe(
      tap((params) => { this.readParams(params); this.loading.set(true); this.failure.set(null); this.historyFailure.set(null); }),
      switchMap((params) => {
        const version = this.positive(params.get('version'), 0) || undefined;
        return forkJoin({
          report: this.api.get(this.reportId, version),
          history: this.api.versions(this.reportId, this.historyPage(), this.pageSize()).pipe(
            map((value) => ({ value, failure: null })),
            catchError((failure: ApiFailure) => of({ value: null, failure }))
          )
        }).pipe(map((value) => ({ value, failure: null })), catchError((failure: ApiFailure) => of({ value: null, failure })));
      }),
      takeUntilDestroyed()
    ).subscribe(({ value, failure }) => {
      this.report.set(value?.report ?? null); this.history.set(value?.history.value ?? null);
      this.historyFailure.set(value?.history.failure ?? null); this.failure.set(failure); this.loading.set(false);
    });
  }

  selectTab(tab: ReportTab): void { void this.router.navigate([], { relativeTo: this.route, queryParams: { tab, page: 1 }, queryParamsHandling: 'merge' }); }
  onTabKeydown(event: KeyboardEvent): void {
    const tabs: ReportTab[] = ['summary', 'data', 'history'];
    const current = tabs.indexOf(this.tab());
    const index = event.key === 'ArrowRight' ? (current + 1) % tabs.length : event.key === 'ArrowLeft' ? (current - 1 + tabs.length) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1;
    if (index < 0) return;
    event.preventDefault();
    this.selectTab(tabs[index]);
    (event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('[role="tab"]')[index]?.focus();
  }
  changeRowPage(page: number): void { void this.router.navigate([], { relativeTo: this.route, queryParams: { page }, queryParamsHandling: 'merge' }); }
  changeHistoryPage(page: number): void { void this.router.navigate([], { relativeTo: this.route, queryParams: { historyPage: page }, queryParamsHandling: 'merge' }); }
  selectVersion(version: number): void { void this.router.navigate([], { relativeTo: this.route, queryParams: { version, tab: 'summary', page: 1 }, queryParamsHandling: 'merge' }); }
  back(): void { void this.router.navigateByUrl(this.returnUrl()); }
  export(): void {
    const item = this.report(); if (!item || !this.canExport()) return;
    this.exporting.set(true); this.exportFailure.set(null);
    this.api.export(item.report_id, item.version, this.selectedFormat()).subscribe({
      next: (response) => { this.exporting.set(false); this.save(response.body, this.filename(response.headers.get('content-disposition'), item)); },
      error: (failure: ApiFailure) => { this.exporting.set(false); this.exportFailure.set(failure); }
    });
  }
  openCancel(): void { this.cancelReason.set(''); this.cancelFailure.set(null); this.cancelOpen.set(true); }
  closeCancel(): void { if (!this.cancelBusy()) this.cancelOpen.set(false); }
  cancel(event: Event): void {
    event.preventDefault(); const item = this.report(); const reason = this.cancelReason().trim();
    if (!item || !reason) return;
    this.cancelBusy.set(true); this.cancelFailure.set(null);
    this.api.cancel(item.report_id, item.version, reason).subscribe({
      next: (version) => { this.cancelBusy.set(false); this.cancelOpen.set(false); this.report.set({ ...item, ...version }); },
      error: (failure: ApiFailure) => { this.cancelBusy.set(false); this.cancelFailure.set(failure); }
    });
  }
  typeLabel(value: ReportType): string { return this.i18n.t(REPORT_TYPE_KEYS[value]); }
  stateLabel(value: ReportState): string { return this.i18n.t(REPORT_STATE_KEYS[value]); }
  completenessLabel(value: ReportCompleteness | null): string { return value ? this.i18n.t(REPORT_COMPLETENESS_KEYS[value]) : this.i18n.t('common.notAvailable'); }
  dataStateLabel(value: string): string { return this.i18n.t(REPORT_DATA_STATE_KEYS[value] ?? 'common.notAvailable'); }
  priorityLabel(value: string | null): string { return value ? this.i18n.t(PENDING_PRIORITY_KEYS[value] ?? 'common.notAvailable') : this.i18n.t('common.notAvailable'); }
  tone(item: ReportVersion): UiState { if (item.state === 'failed') return 'error'; if (item.completeness === 'partial') return 'partial'; if (this.isStale()) return 'stale'; if (item.state === 'cancelled') return 'unavailable'; return 'success'; }
  workorderData(): WorkorderReportData | null { const data = this.report()?.data; return data?.kind === 'workorder_consolidated' ? data : null; }
  oqcData(): OqcReportData | null { const data = this.report()?.data; return data?.kind === 'oqc_summary' ? data : null; }
  workorder(row: WorkorderReportRow | OqcReportRow): WorkorderReportRow { return row as WorkorderReportRow; }
  oqc(row: WorkorderReportRow | OqcReportRow): OqcReportRow { return row as OqcReportRow; }
  display(value: string | number | boolean | null | undefined): string { if (value === null || value === undefined || value === '') return this.i18n.t('common.notAvailable'); if (typeof value === 'boolean') return this.i18n.t(value ? 'common.yes' : 'common.no'); return typeof value === 'number' ? this.i18n.formatNumber(value) : value; }
  filterEntries(): Array<[string, string]> {
    const labels: Record<string, string> = {
      date_from: this.i18n.t('reports.dateFrom'), date_to: this.i18n.t('reports.dateTo'),
      state: this.i18n.t('reports.dataState'), workorder_number: 'Workorder',
      lot_number: this.i18n.t('queries.lot'), priority: this.i18n.t('pending.priority')
    };
    return Object.entries(this.report()?.filters ?? {}).map(([key, value]) => {
      if (key === 'state') return [labels[key], this.dataStateLabel(String(value))];
      if (key === 'priority') return [labels[key], this.priorityLabel(String(value))];
      if ((key === 'date_from' || key === 'date_to') && typeof value === 'string') return [labels[key], this.i18n.formatDate(`${value}T12:00:00Z`, { dateStyle: 'medium' })];
      return [labels[key] ?? key, String(value)];
    });
  }
  countEntries(value: Record<string, number> | undefined): Array<[string, number]> { return Object.entries(value ?? {}); }
  failureTitle(failure = this.failure()): string { if (failure?.kind === 'not-found') return this.i18n.t('reports.notFoundTitle'); return this.i18n.t(failure?.kind === 'forbidden' ? 'reports.forbiddenTitle' : failure?.kind === 'unavailable' ? 'reports.unavailableTitle' : 'reports.errorTitle'); }
  failureMessage(failure = this.failure()): string { if (failure?.kind === 'not-found') return this.i18n.t('reports.notFound'); return this.i18n.t(failure?.kind === 'forbidden' ? 'reports.forbidden' : failure?.kind === 'unavailable' ? 'reports.unavailable' : 'reports.error'); }
  currentUrl(): string { return this.router.url; }

  private readParams(params: ParamMap): void { this.tab.set(this.validTab(params.get('tab'))); this.rowPage.set(this.positive(params.get('page'), 1)); this.pageSize.set(this.positive(params.get('pageSize'), 25, [10, 25, 50])); this.historyPage.set(this.positive(params.get('historyPage'), 1)); }
  private validTab(value: string | null): ReportTab { return value === 'data' || value === 'history' ? value : 'summary'; }
  private positive(value: string | null, fallback: number, allowed?: number[]): number { const parsed = Number(value); return Number.isInteger(parsed) && parsed > 0 && (!allowed || allowed.includes(parsed)) ? parsed : fallback; }
  private toState(failure: ApiFailure | null): UiState | null { if (!failure || failure.kind === 'unauthorized') return null; if (failure.kind === 'forbidden') return 'forbidden'; if (failure.kind === 'unavailable') return 'unavailable'; return 'error'; }
  private safeReturnUrl(value: string | null): string { return value?.startsWith('/reports') && !value.startsWith('//') ? value : '/reports'; }
  private filename(header: string | null, item: ReportDetail): string { const match = header?.match(/filename="([^"]+)"/i); return match?.[1] ?? `${item.report_type}-${item.report_id}-v${item.version}.${this.selectedFormat()}`; }
  private save(blob: Blob | null, filename: string): void { if (!blob) return; const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url); }
}
