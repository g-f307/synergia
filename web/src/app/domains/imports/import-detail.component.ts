import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { FileInspection, ImportStatus, PipelineSummary } from './import.models';
import { ImportService } from './import.service';

const STATUS_KEYS: Record<string, TranslationKey> = {
  completed: 'imports.status.completed', completed_with_errors: 'imports.status.completedWithErrors',
  validation_failed: 'imports.status.validationFailed', failed: 'imports.status.failed',
  duplicate: 'imports.status.duplicate', processing: 'imports.status.processing', received: 'imports.status.received'
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
  archive_path_traversal: 'imports.reason.archivePathTraversal', encrypted_archive: 'imports.reason.encryptedArchive'
};
type AuxiliaryState = 'loading' | 'ready' | 'missing' | 'forbidden' | 'unavailable' | 'error';

@Component({
  imports: [RouterLink],
  template: `
    <section class="import-detail" aria-labelledby="import-detail-title">
      <header class="detail-toolbar">
        <a class="back-link" routerLink="/imports/new"><span aria-hidden="true">←</span>{{ i18n.t('imports.newAnother') }}</a>
        <h1 id="import-detail-title">{{ i18n.t('imports.detailTitle') }}</h1>
      </header>

      <div class="detail-scroll">
        @if (loading()) { <p class="state-copy" role="status">{{ i18n.t('imports.detailLoading') }}</p> }
        @if (failure()) { <section class="failure-state" role="alert"><h2>{{ i18n.t('imports.detailError') }}</h2><p>{{ failure()?.message }}</p>@if(failure()?.correlationId){<p class="technical">{{ i18n.t('imports.correlation') }}: {{ failure()?.correlationId }}</p>}</section> }
        @if (item(); as current) {
          <section class="overview" [attr.aria-label]="i18n.t('imports.result')">
            <div class="status-summary">
              <div><small>{{ i18n.t('imports.status') }}</small><strong class="status-pill" [attr.data-status]="current.status">{{ statusLabel(current.status) }}</strong></div>
            </div>
            <dl class="metadata">
              <div><dt>{{ i18n.t('imports.execution') }}</dt><dd><a data-testid="related-execution" class="technical metadata-link" [routerLink]="['/executions',current.execution_id]" [queryParams]="{from:'/imports/'+current.execution_id}">{{ current.execution_id }}<span aria-hidden="true">›</span></a></dd></div>
              <div><dt>{{ i18n.t('imports.source') }}</dt><dd>{{ current.source }}</dd></div>
              <div><dt>{{ i18n.t('imports.file') }}</dt><dd>{{ current.file_name || i18n.t('common.notAvailable') }}</dd></div>
              <div><dt>{{ i18n.t('imports.startedAt') }}</dt><dd>{{ i18n.formatDate(current.started_at, { dateStyle: 'medium', timeStyle: 'short' }) }}</dd></div>
            </dl>
          </section>

          @if (partial()) { <div class="partial-notice" role="status"><strong>{{ i18n.t('imports.partialTitle') }}</strong><span>{{ i18n.t('imports.partialMessage') }}</span></div> }

          <section class="detail-section summary-section"><header><h2>{{ i18n.t('imports.summaryTitle') }}</h2></header>
          @switch (summaryState()) {
            @case ('loading') { <p role="status">{{ i18n.t('imports.summaryLoading') }}</p> }
            @case ('ready') { @if (summary(); as totals) { <dl class="summary"><div><dt>{{ i18n.t('imports.rowsRead') }}</dt><dd>{{ i18n.formatNumber(totals.rows_read) }}</dd></div><div><dt>{{ i18n.t('imports.validRecords') }}</dt><dd>{{ i18n.formatNumber(totals.valid_records) }}</dd></div><div><dt>{{ i18n.t('imports.rejectedRecords') }}</dt><dd>{{ i18n.formatNumber(totals.rejected_records) }}</dd></div><div><dt>{{ i18n.t('imports.warnings') }}</dt><dd>{{ i18n.formatNumber(totals.warnings) }}</dd></div></dl> } }
            @case ('missing') { <p>{{ i18n.t('imports.summaryPending') }}</p> }
            @case ('forbidden') { <p class="error" role="alert">{{ i18n.t('imports.summaryForbidden') }}</p> }
            @case ('unavailable') { <p class="error" role="alert">{{ i18n.t('imports.summaryUnavailable') }}</p> }
            @case ('error') { <p class="error" role="alert">{{ i18n.t('imports.summaryError') }}</p> }
          }
          @if (summaryFailure()?.correlationId) { <p class="technical">{{ i18n.t('imports.correlation') }}: {{ summaryFailure()?.correlationId }}</p> }
          </section>

          <section class="detail-section inspection-section"><header><h2>{{ i18n.t('imports.inspectionTitle') }}</h2></header>
            @switch (inspectionState()) {
              @case ('loading') { <p role="status">{{ i18n.t('imports.inspectionLoading') }}</p> }
              @case ('ready') {
                @if (!inspections().length) { <p class="empty-copy">{{ i18n.t('imports.noInspection') }}</p> }
                <div class="inspection-list">@for (inspection of inspections(); track inspection.inspection_id) {
                  <article>
                    <div><strong>{{ inspection.original_file_name }}</strong><p>{{ reasonLabel(inspection.reason_code) }}</p></div>
                    <span class="decision-pill" [attr.data-decision]="inspection.decision">{{ decisionLabel(inspection) }}</span>
                    @if (isQuarantined(inspection)) { <p class="inspection-alert">{{ i18n.t('imports.quarantinedUntil', { date: i18n.formatDate(inspection.retained_until!, { dateStyle: 'medium', timeStyle: 'short' }) }) }}</p> }
                    @if (inspection.discarded_at) { <p class="inspection-alert">{{ i18n.t('imports.quarantineDiscarded') }}</p> }
                  </article>
                }</div>
              }
              @case ('missing') { <p class="empty-copy">{{ i18n.t('imports.inspectionPending') }}</p> }
              @case ('forbidden') { <p class="error" role="alert">{{ i18n.t('imports.inspectionForbidden') }}</p> }
              @case ('unavailable') { <p class="error" role="alert">{{ i18n.t('imports.inspectionUnavailable') }}</p> }
              @case ('error') { <p class="error" role="alert">{{ i18n.t('imports.inspectionError') }}</p> }
            }
            @if (inspectionFailure()?.correlationId) { <p class="technical correlation">{{ i18n.t('imports.correlation') }}: {{ inspectionFailure()?.correlationId }}</p> }
          </section>

          <nav class="actions" [attr.aria-label]="i18n.t('imports.newAnother')"><a routerLink="/imports/new">{{ i18n.t('imports.newAnother') }}<span aria-hidden="true">→</span></a></nav>
        }
      </div>
    </section>
  `,
  styleUrl: './import-detail.component.css'
})
export class ImportDetailComponent implements OnInit {
  readonly i18n = inject(I18nService);
  private readonly route = inject(ActivatedRoute);
  private readonly imports = inject(ImportService);
  readonly loading = signal(true);
  readonly item = signal<ImportStatus | null>(null);
  readonly inspections = signal<FileInspection[]>([]);
  readonly summary = signal<PipelineSummary | null>(null);
  readonly failure = signal<ApiFailure | null>(null);
  readonly inspectionState = signal<AuxiliaryState>('loading');
  readonly summaryState = signal<AuxiliaryState>('loading');
  readonly inspectionFailure = signal<ApiFailure | null>(null);
  readonly summaryFailure = signal<ApiFailure | null>(null);
  readonly partial = computed(() => {
    const incomplete: AuxiliaryState[] = ['missing', 'forbidden', 'unavailable', 'error'];
    return !!this.item() && (
      incomplete.includes(this.inspectionState()) || incomplete.includes(this.summaryState())
    );
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('executionId') ?? '';
    this.imports.get(id).subscribe({
      next: (item) => { this.item.set(item); this.loading.set(false); this.loadAuxiliary(id); },
      error: (failure: ApiFailure) => { this.failure.set(failure); this.loading.set(false); }
    });
  }

  private loadAuxiliary(id: string): void {
    this.imports.inspections(id).subscribe({
      next: (items) => { this.inspections.set(items); this.inspectionState.set('ready'); },
      error: (failure: ApiFailure) => { this.inspectionFailure.set(failure); this.inspectionState.set(this.auxiliaryState(failure)); }
    });
    this.imports.summary(id).subscribe({
      next: (summary) => { this.summary.set(summary); this.summaryState.set('ready'); },
      error: (failure: ApiFailure) => { this.summaryFailure.set(failure); this.summaryState.set(this.auxiliaryState(failure)); }
    });
  }

  private auxiliaryState(failure: ApiFailure): AuxiliaryState {
    if (failure.kind === 'not-found') return 'missing';
    if (failure.kind === 'forbidden') return 'forbidden';
    if (failure.kind === 'unavailable') return 'unavailable';
    return 'error';
  }

  statusLabel(status: string): string {
    return this.i18n.t(STATUS_KEYS[status] ?? 'imports.status.unknown');
  }
  decisionLabel(item: FileInspection): string {
    return this.i18n.t(DECISION_KEYS[item.decision] ?? 'imports.decision.unknown');
  }
  reasonLabel(reason: string): string {
    return this.i18n.t(REASON_KEYS[reason] ?? 'imports.reason.unknown');
  }
  isQuarantined(item: FileInspection): boolean {
    return item.decision === 'rejected' && !!item.retained_until && !item.discarded_at;
  }
}
