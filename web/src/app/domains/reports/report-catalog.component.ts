import { Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, ParamMap, Router, RouterLink } from '@angular/router';
import { combineLatest, catchError, map, of, startWith, Subject, switchMap, tap } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { BadgeComponent, ModalComponent, PaginationComponent, ResponsiveTableComponent, StateComponent, UiState } from '../../shared/ui/ui-kit';
import { REPORT_COMPLETENESS_KEYS, REPORT_DATA_STATE_KEYS, REPORT_STATE_KEYS, REPORT_TYPE_KEYS } from './report-labels';
import { CreateReportPayload, ReportCatalogQuery, ReportCompleteness, ReportExportFormat, ReportPage, ReportPolicy, ReportSort, ReportState, ReportType, ReportVersion } from './report.models';
import { ReportService } from './report.service';

@Component({
  selector: 'syn-report-catalog',
  imports: [BadgeComponent, ModalComponent, PaginationComponent, ResponsiveTableComponent, RouterLink, StateComponent],
  templateUrl: './report-catalog.component.html',
  styleUrl: './report-catalog.component.css'
})
export class ReportCatalogComponent {
  readonly i18n = inject(I18nService);
  readonly session = inject(SessionService);
  private readonly api = inject(ReportService);
  private readonly route = inject(ActivatedRoute);
  private readonly refreshRequested = new Subject<void>();
  readonly router = inject(Router);

  readonly organizationId = signal('');
  readonly reportType = signal('');
  readonly stateFilter = signal('');
  readonly executionId = signal('');
  readonly sort = signal<ReportSort>('newest');
  readonly pageSize = signal(25);
  readonly loading = signal(true);
  readonly result = signal<ReportPage | null>(null);
  readonly failure = signal<ApiFailure | null>(null);
  readonly policy = signal<ReportPolicy | null>(null);
  readonly policyFailure = signal<ApiFailure | null>(null);
  readonly downloadFailure = signal<ApiFailure | null>(null);

  readonly generationOpen = signal(false);
  readonly generationBusy = signal(false);
  readonly generationFailure = signal<ApiFailure | null>(null);
  readonly generationError = signal('');
  readonly generationType = signal<ReportType>('workorder_consolidated');
  readonly generationOrganization = signal('');
  readonly generationExecution = signal('');
  readonly referenceAt = signal(this.localNow());
  readonly dateFrom = signal('');
  readonly dateTo = signal('');
  readonly dataState = signal('');
  readonly workorderNumber = signal('');
  readonly lotNumber = signal('');
  readonly priority = signal('');

  readonly canGenerate = computed(() => this.session.hasPermission('report.generate'));
  readonly canExport = computed(() => this.session.hasPermission('report.export') && (this.policy()?.export_formats.includes('csv') ?? false));
  readonly hasPartial = computed(() => this.result()?.items.some((item) => item.completeness === 'partial') ?? false);
  readonly hasStale = computed(() => this.result()?.items.some((item) => this.isStale(item)) ?? false);
  readonly failureState = computed<UiState | null>(() => this.toState(this.failure()));
  readonly policyFailureState = computed<UiState>(() => this.policyFailure()?.kind === 'forbidden' ? 'forbidden' : 'unavailable');

  constructor() {
    this.api.policy().pipe(takeUntilDestroyed()).subscribe({
      next: (policy) => {
        this.policy.set(policy);
        if (policy.generation_organizations.length === 1) this.generationOrganization.set(policy.generation_organizations[0].id);
      },
      error: (failure: ApiFailure) => this.policyFailure.set(failure)
    });
    combineLatest([this.route.queryParamMap, this.refreshRequested.pipe(startWith(undefined))]).pipe(
      tap(([params]) => { this.readParams(params); this.loading.set(true); this.failure.set(null); }),
      switchMap(([params]) => this.api.list(this.query(params)).pipe(
        map((value) => ({ value, failure: null })),
        catchError((failure: ApiFailure) => of({ value: null, failure }))
      )),
      takeUntilDestroyed()
    ).subscribe(({ value, failure }) => {
      this.result.set(value);
      this.failure.set(failure);
      this.loading.set(false);
    });
  }

  apply(event: Event): void { event.preventDefault(); this.navigate(1); }
  changePage(page: number): void { this.navigate(page); }
  clear(): void {
    this.organizationId.set(''); this.reportType.set(''); this.stateFilter.set('');
    this.executionId.set(''); this.sort.set('newest'); this.pageSize.set(25);
    void this.router.navigate([], { relativeTo: this.route, queryParams: {} });
  }
  refresh(): void { this.refreshRequested.next(); }
  openGeneration(): void { this.generationFailure.set(null); this.generationError.set(''); this.generationOpen.set(true); }
  closeGeneration(): void { if (!this.generationBusy()) this.generationOpen.set(false); }
  allowedGenerationStates(): string[] {
    return this.policy()?.report_types.find((item) => item.report_type === this.generationType())?.allowed_states ?? [];
  }
  generate(event: Event): void {
    event.preventDefault();
    this.generationError.set(''); this.generationFailure.set(null);
    if (!this.generationExecution().trim() || !this.generationOrganization() || !this.referenceAt()) {
      this.generationError.set(this.i18n.t('reports.generationRequired'));
      return;
    }
    if (this.dateFrom() && this.dateTo() && this.dateFrom() > this.dateTo()) {
      this.generationError.set(this.i18n.t('reports.invalidPeriod'));
      return;
    }
    const reference = new Date(this.referenceAt());
    if (Number.isNaN(reference.getTime())) {
      this.generationError.set(this.i18n.t('reports.invalidReference'));
      return;
    }
    const filters: CreateReportPayload['filters'] = {};
    if (this.dateFrom()) filters.date_from = this.dateFrom();
    if (this.dateTo()) filters.date_to = this.dateTo();
    if (this.dataState()) filters.state = this.dataState();
    if (this.workorderNumber().trim()) filters.workorder_number = this.workorderNumber().trim();
    if (this.generationType() === 'oqc_summary' && this.lotNumber().trim()) filters.lot_number = this.lotNumber().trim();
    if (this.generationType() === 'oqc_summary' && this.validPriority(this.priority())) filters.priority = this.priority() as CreateReportPayload['filters']['priority'];
    this.generationBusy.set(true);
    this.api.create({
      report_type: this.generationType(), execution_id: this.generationExecution().trim(),
      organization_id: this.generationOrganization(), reference_at: reference.toISOString(), filters
    }).subscribe({
      next: (report) => {
        this.generationBusy.set(false); this.generationOpen.set(false);
        void this.router.navigate(['/reports', report.report_id], { queryParams: { version: report.version, from: this.router.url } });
      },
      error: (failure: ApiFailure) => { this.generationBusy.set(false); this.generationFailure.set(failure); }
    });
  }
  export(item: ReportVersion): void {
    if (!this.canExport() || item.state !== 'succeeded') return;
    this.downloadFailure.set(null);
    this.api.export(item.report_id, item.version, 'csv').subscribe({
      next: (response) => this.save(response.body, this.filename(response.headers.get('content-disposition'), item, 'csv')),
      error: (failure: ApiFailure) => this.downloadFailure.set(failure)
    });
  }
  typeLabel(value: ReportType): string { return this.i18n.t(REPORT_TYPE_KEYS[value]); }
  stateLabel(value: ReportState): string { return this.i18n.t(REPORT_STATE_KEYS[value]); }
  completenessLabel(value: ReportCompleteness | null): string { return value ? this.i18n.t(REPORT_COMPLETENESS_KEYS[value]) : this.i18n.t('common.notAvailable'); }
  dataStateLabel(value: string): string { return this.i18n.t(REPORT_DATA_STATE_KEYS[value] ?? 'common.notAvailable'); }
  tone(item: ReportVersion): UiState { if (item.state === 'failed') return 'error'; if (item.completeness === 'partial') return 'partial'; if (this.isStale(item)) return 'stale'; if (item.state === 'cancelled') return 'unavailable'; return 'success'; }
  isStale(item: ReportVersion): boolean { return item.state === 'generating' && Date.now() - Date.parse(item.created_at) > (this.policy()?.stale_after_seconds ?? 900) * 1000; }
  failureTitle(failure = this.failure()): string { return this.i18n.t(failure?.kind === 'forbidden' ? 'reports.forbiddenTitle' : failure?.kind === 'unavailable' ? 'reports.unavailableTitle' : 'reports.errorTitle'); }
  failureMessage(failure = this.failure()): string { return this.i18n.t(failure?.kind === 'forbidden' ? 'reports.forbidden' : failure?.kind === 'unavailable' ? 'reports.unavailable' : 'reports.error'); }
  policyFailureTitle(): string { return this.i18n.t(this.policyFailure()?.kind === 'forbidden' ? 'reports.forbiddenTitle' : 'reports.policyUnavailableTitle'); }
  policyFailureMessage(): string { return this.i18n.t(this.policyFailure()?.kind === 'forbidden' ? 'reports.forbidden' : 'reports.policyUnavailable'); }

  private readParams(params: ParamMap): void {
    this.organizationId.set(params.get('organization') ?? '');
    this.reportType.set(this.validType(params.get('type')) ?? '');
    this.stateFilter.set(this.validState(params.get('state')) ?? '');
    this.executionId.set(params.get('execution') ?? '');
    this.sort.set(this.validSort(params.get('sort')));
    this.pageSize.set(this.positive(params.get('pageSize'), 25, [10, 25, 50]));
  }
  private query(params: ParamMap): ReportCatalogQuery {
    return { organizationId: this.organizationId() || undefined, reportType: this.validType(this.reportType()), state: this.validState(this.stateFilter()), executionId: this.executionId().trim() || undefined, sort: this.sort(), page: this.positive(params.get('page'), 1), pageSize: this.pageSize() };
  }
  private navigate(page: number): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { organization: this.organizationId() || null, type: this.reportType() || null, state: this.stateFilter() || null, execution: this.executionId().trim() || null, sort: this.sort(), page, pageSize: this.pageSize() } });
  }
  private validType(value: string | null): ReportType | undefined { return value === 'workorder_consolidated' || value === 'oqc_summary' ? value : undefined; }
  private validState(value: string | null): ReportState | undefined { return value === 'generating' || value === 'succeeded' || value === 'failed' || value === 'cancelled' ? value : undefined; }
  private validSort(value: string | null): ReportSort { return value === 'oldest' || value === 'type' ? value : 'newest'; }
  private validPriority(value: string): boolean { return ['critical', 'high', 'normal', 'low'].includes(value); }
  private positive(value: string | null, fallback: number, allowed?: number[]): number { const parsed = Number(value); return Number.isInteger(parsed) && parsed > 0 && (!allowed || allowed.includes(parsed)) ? parsed : fallback; }
  private toState(failure: ApiFailure | null): UiState | null { if (!failure || failure.kind === 'unauthorized') return null; if (failure.kind === 'forbidden') return 'forbidden'; if (failure.kind === 'unavailable') return 'unavailable'; return 'error'; }
  private localNow(): string {
    const now = new Date();
    const localNextMinute = now.getTime() - now.getTimezoneOffset() * 60000 + 60000;
    return new Date(localNextMinute).toISOString().slice(0, 16);
  }
  private filename(header: string | null, item: ReportVersion, format: ReportExportFormat): string { const match = header?.match(/filename="([^"]+)"/i); return match?.[1] ?? `${item.report_type}-${item.report_id}-v${item.version}.${format}`; }
  private save(blob: Blob | null, filename: string): void { if (!blob) return; const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url); }
}
