import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { SessionService } from '../../core/session.service';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { ImportSource, OrganizationOption, UploadPolicy, UploadState, importSources } from './import.models';
import { ImportService } from './import.service';

const STATE_KEYS: Record<UploadState, { title: TranslationKey; message: TranslationKey }> = {
  idle: { title: 'imports.state.idle.title', message: 'imports.state.idle.message' },
  uploading: { title: 'imports.state.uploading.title', message: 'imports.state.uploading.message' },
  inspecting: { title: 'imports.state.inspecting.title', message: 'imports.state.inspecting.message' },
  accepted: { title: 'imports.state.accepted.title', message: 'imports.state.accepted.message' },
  rejected: { title: 'imports.state.rejected.title', message: 'imports.state.rejected.message' },
  duplicate: { title: 'imports.state.duplicate.title', message: 'imports.state.duplicate.message' },
  forbidden: { title: 'imports.state.forbidden.title', message: 'imports.state.forbidden.message' },
  unavailable: { title: 'imports.state.unavailable.title', message: 'imports.state.unavailable.message' },
  error: { title: 'imports.state.error.title', message: 'imports.state.error.message' }
};
const REJECTION_KEYS: Record<string, TranslationKey> = {
  unsupported_extension: 'imports.reason.unsupportedExtension', empty_file: 'imports.reason.emptyFile',
  file_too_large: 'imports.reason.fileTooLarge', declared_mime_mismatch: 'imports.reason.declaredMimeMismatch',
  content_signature_mismatch: 'imports.reason.contentSignatureMismatch', binary_content_mismatch: 'imports.reason.binaryContentMismatch',
  content_type_mismatch: 'imports.reason.contentTypeMismatch', disguised_active_content: 'imports.reason.disguisedActiveContent',
  invalid_text_encoding: 'imports.reason.invalidTextEncoding', corrupted_file: 'imports.reason.corruptedFile',
  macro_or_active_content: 'imports.reason.macroOrActiveContent', embedded_object: 'imports.reason.embeddedObject',
  external_link: 'imports.reason.externalLink', dangerous_formula: 'imports.reason.dangerousFormula',
  path_traversal: 'imports.reason.pathTraversal', archive_too_many_entries: 'imports.reason.archiveTooManyEntries',
  archive_uncompressed_limit: 'imports.reason.archiveUncompressedLimit', archive_compression_ratio: 'imports.reason.archiveCompressionRatio',
  archive_path_traversal: 'imports.reason.archivePathTraversal', encrypted_archive: 'imports.reason.encryptedArchive'
};

@Component({
  imports: [RouterLink],
  template: `
    <section class="imports-page" aria-labelledby="import-title">
      <header class="page-header">
        <p class="eyebrow">{{ i18n.t('imports.eyebrow') }}</p>
        <h1 id="import-title">{{ i18n.t('imports.newTitle') }}</h1>
        <p>{{ i18n.t('imports.introduction') }}</p>
      </header>

      <div class="imports-grid">
        <form class="card" (submit)="submit($event)">
          <label for="import-source">{{ i18n.t('imports.source') }}</label>
          <select id="import-source" [disabled]="busy() || policyLoading()" [value]="source()" (change)="selectSource($any($event.target).value)">
            @for (item of sources; track item) { <option [value]="item">{{ item }}</option> }
          </select>

          @if (!policyLoading() && organizationSelectionRequired()) {
            <label for="import-organization">{{ i18n.t('imports.organization') }}</label>
            <select id="import-organization" [disabled]="busy() || !!policyFailure()" [value]="organizationId()" (change)="organizationId.set($any($event.target).value)">
              <option value="">{{ i18n.t('imports.selectOrganization') }}</option>
              @for (organization of organizationOptions(); track organization.id) {
                <option [value]="organization.id">{{ organization.display_name }} — {{ organization.organization_code }}</option>
              }
            </select>
          }

          <label for="import-file">{{ i18n.t('imports.file') }}</label>
          <input #fileInput id="import-file" type="file" [accept]="acceptedExtensions()"
            [disabled]="busy() || policyLoading() || !!policyFailure()" [attr.aria-describedby]="fileError() ? 'import-file-help import-file-error' : 'import-file-help'"
            [attr.aria-invalid]="fileError() ? true : null" (change)="selectFile($event)">
          <p id="import-file-help" class="help">{{ policyDescription() }}</p>
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
            <li>{{ i18n.t('imports.ruleFormats', { formats: formatsLabel() }) }}</li>
            <li>{{ i18n.t('imports.ruleSize', { size: sizeLabel() }) }}</li>
            <li>{{ i18n.t('imports.ruleInspection') }}</li>
            <li>{{ i18n.t('imports.ruleServer') }}</li>
          </ul>
        </aside>
      </div>

      @if (policyLoading()) { <p role="status">{{ i18n.t('imports.policyLoading') }}</p> }
      @if (policyFailure()) { <div class="card error" role="alert"><strong>{{ i18n.t('imports.policyError') }}</strong>@if(policyFailure()?.correlationId){<p class="technical">{{ i18n.t('imports.correlation') }}: {{ policyFailure()?.correlationId }}</p>}</div> }

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
    .imports-page{display:grid;gap:var(--space-5);max-width:70rem}.page-header{border-bottom:1px solid var(--syn-border);display:block;margin-bottom:0;padding-bottom:var(--syn-space-4)}.imports-grid{display:grid;gap:var(--space-5);grid-template-columns:minmax(18rem,2fr) minmax(16rem,1fr)}
    .help,.rules,p{color:var(--color-muted)}.rules{align-self:start}.selected-file{display:flex;flex-wrap:wrap;gap:var(--space-2);justify-content:space-between;margin:0}
    .result{border-left:.3rem solid var(--color-info)}progress{accent-color:var(--color-brand);inline-size:100%;min-height:1rem}.button-link{display:inline-block;font-weight:700;margin-top:var(--space-3)}
    @media(max-width:48rem){.imports-grid{grid-template-columns:1fr}.rules{order:-1}}
  `]
})
export class ImportCreateComponent implements OnInit {
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
  readonly policies = signal<UploadPolicy[]>([]);
  readonly policyLoading = signal(true);
  readonly policyFailure = signal<ApiFailure | null>(null);
  readonly organizationOptions = signal<OrganizationOption[]>([]);
  readonly permissionOrganizationIds = computed(() => {
    const permission = this.session.profile()?.permissions.find((item) => item.key === 'import.create');
    return permission ? permission.organizations : [];
  });
  readonly organizationId = signal('');
  readonly organizationSelectionRequired = computed(() => {
    const scopes = this.permissionOrganizationIds();
    return scopes === null || scopes.length !== 1 || this.organizationOptions().length !== 1;
  });
  readonly busy = computed(() => this.state() === 'uploading' || this.state() === 'inspecting');
  readonly activePolicy = computed(() => this.policies().find((item) => item.source === this.source()) ?? null);
  readonly acceptedExtensions = computed(() => this.activePolicy()?.allowed_extensions.map((item) => `.${item}`).join(',') ?? '');
  readonly formatsLabel = computed(() => this.activePolicy()?.allowed_extensions.map((item) => item.toUpperCase()).join(', ') || this.i18n.t('common.notAvailable'));
  readonly sizeLabel = computed(() => this.activePolicy() ? this.formatBytes(this.activePolicy()!.max_bytes) : this.i18n.t('common.notAvailable'));
  readonly policyDescription = computed(() => this.activePolicy()
    ? this.i18n.t('imports.fileHelp', { formats: this.formatsLabel(), size: this.sizeLabel() })
    : this.i18n.t('imports.policyLoading'));
  readonly canSubmit = computed(() => !!this.activePolicy() && !!this.file() && !this.fileError() && !this.busy()
    && this.organizationOptions().some((organization) => organization.id === this.organizationId()));
  readonly stateTitle = computed(() => this.i18n.t(STATE_KEYS[this.state()].title));
  readonly stateMessage = computed(() => this.i18n.t(STATE_KEYS[this.state()].message));

  ngOnInit(): void {
    this.imports.policy().subscribe({
      next: (configuration) => {
        this.policies.set(configuration.policies);
        this.organizationOptions.set(configuration.organizations);
        const scopes = this.permissionOrganizationIds();
        const inferred = scopes?.length === 1
          ? configuration.organizations.find((organization) => organization.id === scopes[0])
          : undefined;
        this.organizationId.set(inferred?.id ?? '');
        this.policyLoading.set(false);
      },
      error: (failure: ApiFailure) => { this.policyFailure.set(failure); this.policyLoading.set(false); }
    });
  }

  selectSource(source: ImportSource): void {
    this.source.set(source);
    this.fileError.set(this.validate(this.file()));
  }

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
    this.imports.upload(this.source(), file, this.organizationId()).pipe(finalize(() => {
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
  formatBytes(size: number): string {
    if (size >= 1024 * 1024) return `${this.i18n.formatNumber(size / 1024 / 1024, { maximumFractionDigits: 2 })} MiB`;
    if (size >= 1024) return `${this.i18n.formatNumber(size / 1024, { maximumFractionDigits: 2 })} KiB`;
    return `${this.i18n.formatNumber(size)} B`;
  }

  private validate(file: File | null): string {
    if (!file) return this.i18n.t('imports.validation.required');
    const extension = this.safeName(file.name).split('.').pop()?.toLowerCase() ?? '';
    const policy = this.activePolicy();
    if (!policy) return this.i18n.t('imports.policyError');
    if (!policy.allowed_extensions.includes(extension)) return this.i18n.t('imports.validation.extension', { formats: this.formatsLabel() });
    if (file.size === 0) return this.i18n.t('imports.validation.empty');
    if (file.size > policy.max_bytes) return this.i18n.t('imports.validation.size', { size: this.sizeLabel() });
    return '';
  }

  private handleFailure(failure: ApiFailure): void {
    this.correlationId.set(failure.correlationId);
    const inspectionRejection = failure.code in REJECTION_KEYS;
    this.rejectionReason.set(inspectionRejection ? this.i18n.t(REJECTION_KEYS[failure.code]) : '');
    const executionId = String(failure.details?.['execution_id'] ?? '');
    const duplicateId = String(failure.details?.['duplicate_of_execution_id'] ?? '');
    this.targetExecutionId.set(duplicateId || executionId || null);
    this.state.set(failure.kind === 'conflict' && failure.code === 'duplicate_file'
      ? 'duplicate'
      : inspectionRejection
        ? 'rejected'
        : failure.kind === 'forbidden'
          ? 'forbidden'
          : failure.kind === 'unavailable'
            ? 'unavailable'
            : 'error');
  }
}
