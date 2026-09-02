import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

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
  embedded_object: 'imports.reason.embeddedObject', external_link: 'imports.reason.externalLink', dangerous_formula: 'imports.reason.dangerousFormula'
};

@Component({
  imports: [RouterLink],
  template: `
    <section class="detail" aria-labelledby="import-detail-title">
      <p class="eyebrow">{{ i18n.t('imports.eyebrow') }}</p>
      <h1 id="import-detail-title">{{ i18n.t('imports.detailTitle') }}</h1>
      @if (loading()) { <p role="status">{{ i18n.t('imports.detailLoading') }}</p> }
      @if (failure()) { <div class="card error" role="alert"><h2>{{ i18n.t('imports.detailError') }}</h2><p>{{ failure()?.message }}</p>@if(failure()?.correlationId){<p class="technical">{{ i18n.t('imports.correlation') }}: {{ failure()?.correlationId }}</p>}</div> }
      @if (item(); as current) {
        <div class="grid">
          <section class="card"><h2>{{ i18n.t('imports.result') }}</h2><dl>
            <div><dt>{{ i18n.t('imports.execution') }}</dt><dd class="technical">{{ current.execution_id }}</dd></div>
            <div><dt>{{ i18n.t('imports.status') }}</dt><dd>{{ statusLabel(current.status) }}</dd></div>
            <div><dt>{{ i18n.t('imports.source') }}</dt><dd>{{ current.source }}</dd></div>
            <div><dt>{{ i18n.t('imports.file') }}</dt><dd>{{ current.file_name || i18n.t('common.notAvailable') }}</dd></div>
            <div><dt>{{ i18n.t('imports.startedAt') }}</dt><dd>{{ i18n.formatDate(current.started_at, { dateStyle: 'medium', timeStyle: 'short' }) }}</dd></div>
          </dl></section>
          <section class="card"><h2>{{ i18n.t('imports.inspectionTitle') }}</h2>
            @if (!inspections().length) { <p>{{ i18n.t('imports.noInspection') }}</p> }
            @for (inspection of inspections(); track inspection.inspection_id) {
              <article><strong>{{ inspection.original_file_name }}</strong><p>{{ decisionLabel(inspection) }}</p><p>{{ reasonLabel(inspection.reason_code) }}</p>
                @if (isQuarantined(inspection)) { <p class="error">{{ i18n.t('imports.quarantinedUntil', { date: i18n.formatDate(inspection.retained_until!, { dateStyle: 'medium', timeStyle: 'short' }) }) }}</p> }
                @if (inspection.discarded_at) { <p>{{ i18n.t('imports.quarantineDiscarded') }}</p> }
              </article>
            }
          </section>
        </div>
        @if (summary(); as totals) { <section class="card"><h2>{{ i18n.t('imports.summaryTitle') }}</h2><dl class="summary"><div><dt>{{ i18n.t('imports.rowsRead') }}</dt><dd>{{ i18n.formatNumber(totals.rows_read) }}</dd></div><div><dt>{{ i18n.t('imports.validRecords') }}</dt><dd>{{ i18n.formatNumber(totals.valid_records) }}</dd></div><div><dt>{{ i18n.t('imports.rejectedRecords') }}</dt><dd>{{ i18n.formatNumber(totals.rejected_records) }}</dd></div><div><dt>{{ i18n.t('imports.warnings') }}</dt><dd>{{ i18n.formatNumber(totals.warnings) }}</dd></div></dl></section> }
        <nav class="actions"><a routerLink="/imports/new">{{ i18n.t('imports.newAnother') }}</a></nav>
      }
    </section>
  `,
  styles: [`.detail{display:grid;gap:var(--space-5);max-width:70rem}dl{display:grid;gap:var(--space-3);margin:0}dl div{display:grid;gap:var(--space-1)}dt{color:var(--color-muted);font-weight:600}dd{margin:0;overflow-wrap:anywhere}.summary{grid-template-columns:repeat(auto-fit,minmax(10rem,1fr))}article+article{border-top:1px solid var(--color-border);margin-top:var(--space-3);padding-top:var(--space-3)}article p{margin:.25rem 0}.actions{display:flex;flex-wrap:wrap;gap:var(--space-5);font-weight:700}`]
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

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('executionId') ?? '';
    forkJoin({
      item: this.imports.get(id),
      inspections: this.imports.inspections(id).pipe(catchError(() => of([]))),
      summary: this.imports.summary(id).pipe(catchError(() => of(null)))
    }).subscribe({
      next: (result) => { this.item.set(result.item); this.inspections.set(result.inspections); this.summary.set(result.summary); this.loading.set(false); },
      error: (failure: ApiFailure) => { this.failure.set(failure); this.loading.set(false); }
    });
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
