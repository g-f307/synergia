import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, ParamMap, Router, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { BadgeComponent, PaginationComponent, ResponsiveTableComponent, StateComponent, UiState } from '../../shared/ui/ui-kit';
import { FileInspection, ImportIssuePage, ImportIssueSeverity, ImportResultSummary, ImportStatus } from './import.models';
import { ImportService } from './import.service';
import { ImportTechnicalDetailsComponent } from './import-technical-details.component';
import { IMPORT_ISSUE_KEYS } from './import-issue-labels';

const STATUS_KEYS: Record<string, TranslationKey> = {
  completed: 'imports.status.completed', completed_with_errors: 'imports.status.completedWithErrors',
  validation_failed: 'imports.status.validationFailed', failed: 'imports.status.failed',
  duplicate: 'imports.status.duplicate', processing: 'imports.status.processing', received: 'imports.status.received',
  pending: 'imports.status.received', validating: 'imports.status.processing', normalizing: 'imports.status.processing',
  consolidating: 'imports.status.processing', applying_rules: 'imports.status.processing', reprocessing: 'imports.status.processing',
  cancelled: 'imports.status.cancelled'
};
const DECISION_KEYS: Record<string, TranslationKey> = {
  accepted: 'imports.decision.accepted', rejected: 'imports.decision.rejected'
};
const REASON_KEYS: Record<string, TranslationKey> = {
  accepted: 'imports.reason.accepted', unsupported_extension: 'imports.reason.unsupportedExtension',
  empty_file: 'imports.reason.emptyFile', file_too_large: 'imports.reason.fileTooLarge',
  declared_mime_mismatch: 'imports.reason.declaredMimeMismatch', content_signature_mismatch: 'imports.reason.contentSignatureMismatch',
  binary_content_mismatch: 'imports.reason.binaryContentMismatch', content_type_mismatch: 'imports.reason.contentTypeMismatch',
  disguised_active_content: 'imports.reason.disguisedActiveContent', invalid_text_encoding: 'imports.reason.invalidTextEncoding',
  corrupted_file: 'imports.reason.corruptedFile', macro_or_active_content: 'imports.reason.macroOrActiveContent',
  embedded_object: 'imports.reason.embeddedObject', external_link: 'imports.reason.externalLink', dangerous_formula: 'imports.reason.dangerousFormula',
  path_traversal: 'imports.reason.pathTraversal', archive_too_many_entries: 'imports.reason.archiveTooManyEntries',
  archive_uncompressed_limit: 'imports.reason.archiveUncompressedLimit', archive_compression_ratio: 'imports.reason.archiveCompressionRatio',
  archive_path_traversal: 'imports.reason.archivePathTraversal', encrypted_archive: 'imports.reason.encryptedArchive',
  workbook_sheet_limit: 'imports.reason.capacityExceeded', workbook_row_limit: 'imports.reason.capacityExceeded',
  workbook_column_limit: 'imports.reason.capacityExceeded', workbook_cell_limit: 'imports.reason.capacityExceeded',
  workbook_dimension_limit: 'imports.reason.capacityExceeded', workbook_memory_limit: 'imports.reason.capacityExceeded',
  workbook_metadata_limit: 'imports.reason.capacityExceeded', workbook_formula_limit: 'imports.reason.capacityExceeded',
  ingestion_file_limit: 'imports.reason.capacityExceeded', ingestion_time_limit: 'imports.reason.capacityExceeded',
  ingestion_issue_limit: 'imports.reason.capacityExceeded', no_authorized_sheet: 'imports.reason.noAuthorizedSheet',
  unreadable_workbook: 'imports.reason.unreadableWorkbook'
};
type AuxiliaryState = 'loading' | 'ready' | 'missing' | 'forbidden' | 'unavailable' | 'error';

@Component({
  imports: [RouterLink, StateComponent, BadgeComponent, PaginationComponent, ResponsiveTableComponent, ImportTechnicalDetailsComponent],
  templateUrl: './import-detail.component.html',
  styleUrl: './import-detail.component.css'
})
export class ImportDetailComponent implements OnInit {
  readonly i18n = inject(I18nService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly imports = inject(ImportService);
  private readonly session = inject(SessionService);
  private readonly destroyRef = inject(DestroyRef);
  private id = '';
  private contextRequests = new Subscription();
  private summaryRequest = new Subscription();
  private inspectionRequest = new Subscription();
  private issuesRequest = new Subscription();
  private exportRequest = new Subscription();
  private issuesSignature = '';
  readonly loading = signal(true);
  readonly item = signal<ImportStatus | null>(null);
  readonly inspections = signal<FileInspection[]>([]);
  readonly result = signal<ImportResultSummary | null>(null);
  readonly summary = computed(() => this.result()?.summary ?? null);
  readonly failure = signal<ApiFailure | null>(null);
  readonly inspectionState = signal<AuxiliaryState>('loading');
  readonly summaryState = signal<AuxiliaryState>('loading');
  readonly inspectionFailure = signal<ApiFailure | null>(null);
  readonly summaryFailure = signal<ApiFailure | null>(null);
  readonly issuePage = signal<ImportIssuePage | null>(null);
  readonly issuesLoading = signal(false);
  readonly issuesFailure = signal<ApiFailure | null>(null);
  readonly exportFailure = signal<ApiFailure | null>(null);
  readonly exporting = signal(false);
  readonly severity = signal<ImportIssueSeverity | ''>('');
  readonly requestedPage = signal(1);
  readonly partial = computed(() => !!this.item() && (
    !!this.inspectionFailure() || !!this.summaryFailure() || !!this.issuesFailure()
  ));
  readonly canImport = computed(() => this.session.hasPermission('import.create'));
  readonly canOpenExecution = computed(() => this.session.hasPermission('execution.read'));

  ngOnInit(): void {
    this.destroyRef.onDestroy(() => {
      this.contextRequests.unsubscribe();
      this.summaryRequest.unsubscribe();
      this.inspectionRequest.unsubscribe();
      this.issuesRequest.unsubscribe();
      this.exportRequest.unsubscribe();
    });
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const id = params.get('executionId') ?? '';
      if (id === this.id) return;
      this.id = id;
      this.reset();
      this.readQuery(this.route.snapshot.queryParamMap);
      this.loadImport();
    });
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((query) => {
      this.readQuery(query);
      if (this.item()) this.loadIssues();
    });
  }

  private reset(): void {
    this.contextRequests.unsubscribe();
    this.summaryRequest.unsubscribe();
    this.inspectionRequest.unsubscribe();
    this.issuesRequest.unsubscribe();
    this.exportRequest.unsubscribe();
    this.contextRequests = new Subscription();
    this.issuesSignature = '';
    this.loading.set(true);
    this.item.set(null); this.failure.set(null);
    this.result.set(null); this.summaryFailure.set(null); this.summaryState.set('loading');
    this.inspections.set([]); this.inspectionFailure.set(null); this.inspectionState.set('loading');
    this.issuePage.set(null); this.issuesFailure.set(null); this.issuesLoading.set(false);
    this.exportFailure.set(null); this.exporting.set(false);
  }

  private readQuery(query: ParamMap): void {
    const value = query.get('severity');
    this.severity.set(value === 'error' || value === 'warning' ? value : '');
    const page = Number(query.get('page') ?? 1);
    this.requestedPage.set(Number.isSafeInteger(page) && page > 0 && page <= 2147483647 ? page : 1);
  }

  loadImport(): void {
    if (!this.id || this.item()) return;
    this.loading.set(true); this.failure.set(null);
    this.contextRequests.add(this.imports.get(this.id).subscribe({
      next: (item) => {
        this.item.set(item); this.loading.set(false);
        this.loadSummary(); this.loadInspections(); this.loadIssues();
      },
      error: (failure: ApiFailure) => { this.failure.set(failure); this.loading.set(false); }
    }));
  }

  loadSummary(): void {
    this.summaryRequest.unsubscribe();
    this.summaryState.set('loading'); this.summaryFailure.set(null);
    this.summaryRequest = this.imports.resultSummary(this.id).subscribe({
      next: (result) => { this.result.set(result); this.summaryState.set('ready'); },
      error: (failure: ApiFailure) => { this.summaryFailure.set(failure); this.summaryState.set(this.auxiliaryState(failure)); }
    });
  }

  loadInspections(): void {
    this.inspectionRequest.unsubscribe();
    this.inspectionState.set('loading'); this.inspectionFailure.set(null);
    this.inspectionRequest = this.imports.inspections(this.id).subscribe({
      next: (items) => { this.inspections.set(items); this.inspectionState.set('ready'); },
      error: (failure: ApiFailure) => { this.inspectionFailure.set(failure); this.inspectionState.set(this.auxiliaryState(failure)); }
    });
  }

  refreshResult(): void { this.loadSummary(); this.loadInspections(); this.loadIssues(true); }

  loadIssues(force = false): void {
    const signature = JSON.stringify([this.id, this.requestedPage(), this.severity()]);
    if (signature === this.issuesSignature && !force) return;
    this.issuesSignature = signature;
    this.issuesRequest.unsubscribe();
    this.exportRequest.unsubscribe(); this.exporting.set(false); this.exportFailure.set(null);
    this.issuePage.set(null); this.issuesFailure.set(null); this.issuesLoading.set(true);
    this.issuesRequest = this.imports.issues(this.id, this.requestedPage(), this.severity()).subscribe({
      next: (page) => { this.issuePage.set(page); this.issuesLoading.set(false); },
      error: (failure: ApiFailure) => { this.issuesFailure.set(failure); this.issuesLoading.set(false); }
    });
  }

  filterSeverity(value: string): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { severity: value === 'error' || value === 'warning' ? value : null, page: 1 }, queryParamsHandling: 'merge' });
  }
  goToPage(page: number): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { page }, queryParamsHandling: 'merge' });
  }

  exportCsv(): void {
    if (this.exporting() || this.issuesLoading() || !this.issuePage()?.pagination.total) return;
    this.exporting.set(true); this.exportFailure.set(null);
    this.exportRequest = this.imports.issuesCsv(this.id, this.severity()).subscribe({
      next: (blob) => {
        let url: string | null = null;
        try {
          url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url; anchor.download = 'import-issues.csv'; anchor.click();
        } catch {
          this.exportFailure.set({ kind: 'internal', status: 0, code: 'download_failed', message: '', correlationId: null, fields: [] });
        } finally {
          if (url) URL.revokeObjectURL(url);
          this.exporting.set(false);
        }
      },
      error: (failure: ApiFailure) => { this.exportFailure.set(failure); this.exporting.set(false); }
    });
  }

  private auxiliaryState(failure: ApiFailure): AuxiliaryState {
    if (failure.kind === 'not-found') return 'missing';
    if (failure.kind === 'forbidden') return 'forbidden';
    if (failure.kind === 'unavailable') return 'unavailable';
    return 'error';
  }
  failureState(failure: ApiFailure): UiState {
    if (failure.kind === 'forbidden') return 'forbidden';
    if (failure.kind === 'unavailable') return 'unavailable';
    if (failure.kind === 'not-found') return 'empty';
    return 'error';
  }
  failureMessage(section: 'summary' | 'inspection' | 'issues' | 'export', failure: ApiFailure): string {
    if (failure.kind === 'unauthorized') return this.i18n.t('imports.sessionRequired');
    const keys: Record<typeof section, Record<string, TranslationKey>> = {
      summary: { forbidden: 'imports.summaryForbidden', 'not-found': 'imports.summaryNotFound', unavailable: 'imports.summaryUnavailable', error: 'imports.summaryError' },
      inspection: { forbidden: 'imports.inspectionForbidden', 'not-found': 'imports.inspectionPending', unavailable: 'imports.inspectionUnavailable', error: 'imports.inspectionError' },
      issues: { forbidden: 'imports.issues.forbidden', 'not-found': 'imports.issues.notFound', unavailable: 'imports.issues.unavailable', error: 'imports.issues.error' },
      export: { forbidden: 'imports.issues.exportForbidden', 'not-found': 'imports.issues.notFound', unavailable: 'imports.issues.exportUnavailable', error: 'imports.issues.exportError' }
    };
    return this.i18n.t(keys[section][failure.kind] ?? keys[section]['error']);
  }
  issueReason(code: string): string { return this.i18n.t(IMPORT_ISSUE_KEYS[code] ?? 'imports.issueReason.unmapped_issue'); }
  statusLabel(status: string): string { return this.i18n.t(STATUS_KEYS[status] ?? 'imports.status.unknown'); }
  decisionLabel(item: FileInspection): string { return this.i18n.t(DECISION_KEYS[item.decision] ?? 'imports.decision.unknown'); }
  reasonLabel(reason: string): string { return this.i18n.t(REASON_KEYS[reason] ?? 'imports.reason.unknown'); }
  isQuarantined(item: FileInspection): boolean { return item.decision === 'rejected' && !!item.retained_until && !item.discarded_at; }
}
