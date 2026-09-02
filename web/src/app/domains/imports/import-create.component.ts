import { Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { ImportSource, UploadState, importSources } from './import.models';
import { ImportService } from './import.service';

const MAX_FILE_SIZE = 25 * 1024 * 1024;
const ALLOWED_EXTENSIONS = ['csv', 'json', 'xlsx'];
const STATE_KEYS: Record<UploadState, { title: TranslationKey; message: TranslationKey }> = {
  idle: { title: 'imports.state.idle.title', message: 'imports.state.idle.message' },
  uploading: { title: 'imports.state.uploading.title', message: 'imports.state.uploading.message' },
  inspecting: { title: 'imports.state.inspecting.title', message: 'imports.state.inspecting.message' },
  accepted: { title: 'imports.state.accepted.title', message: 'imports.state.accepted.message' },
  rejected: { title: 'imports.state.rejected.title', message: 'imports.state.rejected.message' },
  duplicate: { title: 'imports.state.duplicate.title', message: 'imports.state.duplicate.message' },
  error: { title: 'imports.state.error.title', message: 'imports.state.error.message' }
};
const REJECTION_KEYS: Record<string, TranslationKey> = {
  unsupported_extension: 'imports.reason.unsupportedExtension', empty_file: 'imports.reason.emptyFile',
  file_too_large: 'imports.reason.fileTooLarge', declared_mime_mismatch: 'imports.reason.declaredMimeMismatch',
  content_signature_mismatch: 'imports.reason.contentSignatureMismatch', binary_content_mismatch: 'imports.reason.binaryContentMismatch',
  content_type_mismatch: 'imports.reason.contentTypeMismatch', disguised_active_content: 'imports.reason.disguisedActiveContent',
  invalid_text_encoding: 'imports.reason.invalidTextEncoding', corrupted_file: 'imports.reason.corruptedFile',
  macro_or_active_content: 'imports.reason.macroOrActiveContent', embedded_object: 'imports.reason.embeddedObject',
  external_link: 'imports.reason.externalLink', dangerous_formula: 'imports.reason.dangerousFormula'
};

@Component({
  imports: [RouterLink],
  template: `
    <section class="imports-page" aria-labelledby="import-title">
      <header>
        <p class="eyebrow">{{ i18n.t('imports.eyebrow') }}</p>
        <h1 id="import-title">{{ i18n.t('imports.newTitle') }}</h1>
        <p>{{ i18n.t('imports.introduction') }}</p>
      </header>

      <div class="imports-grid">
        <form class="card" (submit)="submit($event)">
          <label for="import-source">{{ i18n.t('imports.source') }}</label>
          <select id="import-source" [disabled]="busy()" [value]="source()" (change)="source.set($any($event.target).value)">
            @for (item of sources; track item) { <option [value]="item">{{ item }}</option> }
          </select>

          @if (organizationOptions().length > 1) {
            <label for="import-organization">{{ i18n.t('imports.organization') }}</label>
            <select id="import-organization" [disabled]="busy()" [value]="organizationId()" (change)="organizationId.set($any($event.target).value)">
              <option value="">{{ i18n.t('imports.selectOrganization') }}</option>
              @for (id of organizationOptions(); track id) { <option [value]="id">{{ shortId(id) }}</option> }
            </select>
          }

          <label for="import-file">{{ i18n.t('imports.file') }}</label>
          <input #fileInput id="import-file" type="file" accept=".csv,.json,.xlsx"
            [disabled]="busy()" [attr.aria-describedby]="fileError() ? 'import-file-help import-file-error' : 'import-file-help'"
            [attr.aria-invalid]="fileError() ? true : null" (change)="selectFile($event)">
          <p id="import-file-help" class="help">{{ i18n.t('imports.fileHelp') }}</p>
          @if (fileError()) { <p id="import-file-error" class="error" role="alert">{{ fileError() }}</p> }
          @if (file(); as selected) {
            <p class="selected-file"><strong>{{ safeName(selected.name) }}</strong><span>{{ formatBytes(selected.size) }}</span></p>
          }

          <button type="submit" [disabled]="!canSubmit()" [attr.aria-busy]="busy()">
            {{ i18n.t(busy() ? 'imports.submitting' : 'imports.submit') }}
          </button>
        </form>

        <aside class="card rules" aria-labelledby="import-rules-title">
          <h2 id="import-rules-title">{{ i18n.t('imports.rulesTitle') }}</h2>
          <ul>
            <li>{{ i18n.t('imports.ruleFormats') }}</li>
            <li>{{ i18n.t('imports.ruleSize') }}</li>
            <li>{{ i18n.t('imports.ruleInspection') }}</li>
            <li>{{ i18n.t('imports.ruleServer') }}</li>
          </ul>
        </aside>
      </div>

      @if (state() !== 'idle') {
        <section class="card result" role="status" aria-live="polite">
          <h2>{{ stateTitle() }}</h2>
          <p>{{ stateMessage() }}</p>
          @if (rejectionReason()) { <p class="error"><strong>{{ rejectionReason() }}</strong></p> }
          @if (state() === 'uploading') {
            <progress [attr.aria-label]="i18n.t('imports.progressLabel')" [value]="progress() ?? undefined" [max]="progress() === null ? undefined : 100">
              {{ progress() === null ? i18n.t('imports.progressUnknown') : progress() + '%' }}
            </progress>
          }
          @if (correlationId()) { <p class="technical">{{ i18n.t('imports.correlation') }}: {{ correlationId() }}</p> }
          @if (targetExecutionId()) {
            <a class="button-link" [routerLink]="['/imports', targetExecutionId()]">{{ i18n.t('imports.viewResult') }}</a>
          }
        </section>
      }
    </section>
  `,
  styles: [`
    .imports-page{display:grid;gap:var(--space-5);max-width:70rem}.imports-grid{display:grid;gap:var(--space-5);grid-template-columns:minmax(18rem,2fr) minmax(16rem,1fr)}
    .help,.rules,p{color:var(--color-muted)}.rules{align-self:start}.selected-file{display:flex;flex-wrap:wrap;gap:var(--space-2);justify-content:space-between;margin:0}
    .result{border-left:.3rem solid var(--color-info)}progress{accent-color:var(--color-brand);inline-size:100%;min-height:1rem}.button-link{display:inline-block;font-weight:700;margin-top:var(--space-3)}
    @media(max-width:48rem){.imports-grid{grid-template-columns:1fr}}
  `]
})
export class ImportCreateComponent {
  readonly i18n = inject(I18nService);
  private readonly imports = inject(ImportService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  readonly sources = importSources;
  readonly source = signal<ImportSource>('N-FP');
  readonly file = signal<File | null>(null);
  readonly fileError = signal('');
  readonly state = signal<UploadState>('idle');
  readonly progress = signal<number | null>(null);
  readonly correlationId = signal<string | null>(null);
  readonly rejectionReason = signal('');
  readonly targetExecutionId = signal<string | null>(null);
  readonly organizationOptions = computed(() => this.session.profile()?.permissions.find((item) => item.key === 'import.create')?.organizations ?? []);
  readonly organizationId = signal('');
  readonly busy = computed(() => this.state() === 'uploading' || this.state() === 'inspecting');
  readonly canSubmit = computed(() => !!this.file() && !this.fileError() && !this.busy() && (this.organizationOptions().length <= 1 || !!this.organizationId()));
  readonly stateTitle = computed(() => this.i18n.t(STATE_KEYS[this.state()].title));
  readonly stateMessage = computed(() => this.i18n.t(STATE_KEYS[this.state()].message));

  selectFile(event: Event): void {
    const selected = (event.target as HTMLInputElement).files?.[0] ?? null;
    this.file.set(selected);
    this.fileError.set(this.validate(selected));
    this.state.set('idle');
    this.targetExecutionId.set(null);
  }

  submit(event: Event): void {
    event.preventDefault();
    const file = this.file();
    if (!file || !this.canSubmit()) return;
    this.state.set('uploading');
    this.progress.set(0);
    this.correlationId.set(null);
    this.rejectionReason.set('');
    const options = this.organizationOptions();
    const organization = options.length === 1 ? options[0] : this.organizationId() || undefined;
    this.imports.upload(this.source(), file, organization).pipe(finalize(() => {
      if (this.state() === 'uploading') this.state.set('inspecting');
    })).subscribe({
      next: (update) => {
        if (update.kind === 'progress') {
          this.progress.set(update.progress);
          if (update.progress === 100) this.state.set('inspecting');
          return;
        }
        this.state.set('accepted');
        this.targetExecutionId.set(update.result.execution_id);
        void this.router.navigate(['/imports', update.result.execution_id]);
      },
      error: (failure: ApiFailure) => this.handleFailure(failure)
    });
  }

  safeName(name: string): string { return name.replaceAll('\\', '/').split('/').pop() || this.i18n.t('common.notAvailable'); }
  shortId(id: string): string { return `${id.slice(0, 8)}…`; }
  formatBytes(size: number): string { return this.i18n.formatNumber(size / 1024 / 1024, { maximumFractionDigits: 2 }) + ' MB'; }

  private validate(file: File | null): string {
    if (!file) return this.i18n.t('imports.validation.required');
    const extension = this.safeName(file.name).split('.').pop()?.toLowerCase() ?? '';
    if (!ALLOWED_EXTENSIONS.includes(extension)) return this.i18n.t('imports.validation.extension');
    if (file.size === 0) return this.i18n.t('imports.validation.empty');
    if (file.size > MAX_FILE_SIZE) return this.i18n.t('imports.validation.size');
    return '';
  }

  private handleFailure(failure: ApiFailure): void {
    this.correlationId.set(failure.correlationId);
    this.rejectionReason.set(failure.details?.['execution_id']
      ? this.i18n.t(REJECTION_KEYS[failure.code] ?? 'imports.reason.unknown')
      : '');
    const executionId = String(failure.details?.['execution_id'] ?? '');
    const duplicateId = String(failure.details?.['duplicate_of_execution_id'] ?? '');
    this.targetExecutionId.set(duplicateId || executionId || null);
    this.state.set(failure.kind === 'conflict' ? 'duplicate' : executionId ? 'rejected' : 'error');
  }
}
