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
      <h1 id="import-title" class="sr-only">{{ i18n.t('imports.newTitle') }}</h1>

      <div class="import-workspace">
        <header class="workspace-heading">
          <div><h2>{{ i18n.t('imports.workspaceTitle') }}</h2><p>{{ i18n.t('imports.introduction') }}</p></div>
        </header>

        <aside class="trust-panel" aria-labelledby="import-rules-title">
          <header><h2 id="import-rules-title">{{ i18n.t('imports.rulesTitle') }}</h2></header>
          <div class="trust-grid">
            <div class="trust-item"><span>{{ i18n.t('imports.ruleFormats', { formats: formatsLabel() }) }}</span></div>
            <div class="trust-item"><span>{{ i18n.t('imports.ruleSize', { size: sizeLabel() }) }}</span></div>
            <div class="trust-item"><span>{{ i18n.t('imports.ruleInspection') }}</span></div>
            <div class="trust-item"><span>{{ i18n.t('imports.ruleServer') }}</span></div>
          </div>
        </aside>

        <form class="upload-form" (submit)="submit($event)">
          <div class="workflow-grid">
            <section class="workflow-step source-step" aria-labelledby="source-step-title">
              <header><span aria-hidden="true">1</span><div><h3 id="source-step-title">{{ i18n.t('imports.sourceStepTitle') }}</h3><p>{{ i18n.t('imports.sourceHint') }}</p></div></header>
              <label class="field-label" for="import-source">{{ i18n.t('imports.source') }}</label>
              <select id="import-source" name="source" autocomplete="off" [disabled]="busy() || policyLoading()" [value]="source()" (change)="selectSource($any($event.target).value)">
                @for (item of sources; track item) { <option [value]="item" translate="no">{{ item }}</option> }
              </select>
              @if (!policyLoading() && organizationSelectionRequired()) {
                <label class="field-label" for="import-organization">{{ i18n.t('imports.organization') }}</label>
                <select id="import-organization" name="organization" autocomplete="off" [disabled]="busy() || !!policyFailure()" [value]="organizationId()" (change)="organizationId.set($any($event.target).value)">
                  <option value="">{{ i18n.t('imports.selectOrganization') }}</option>
                  @for (organization of organizationOptions(); track organization.id) { <option [value]="organization.id">{{ organization.display_name }} — {{ organization.organization_code }}</option> }
                </select>
              }
            </section>

            <section class="workflow-step file-step" aria-labelledby="file-step-title">
              <header><span aria-hidden="true">2</span><div><h3 id="file-step-title">{{ i18n.t('imports.file') }}</h3><p id="import-file-help">{{ policyDescription() }}</p></div></header>
              <div class="file-control">
                <input #fileInput class="file-input" id="import-file" name="file" autocomplete="off" type="file" [accept]="acceptedExtensions()"
                  [disabled]="busy() || policyLoading() || !!policyFailure()" [attr.aria-describedby]="fileError() ? 'import-file-help import-file-error' : 'import-file-help'"
                  [attr.aria-invalid]="fileError() ? true : null" (change)="selectFile($event)">
                <label class="file-picker" for="import-file">
                  <img src="/assets/icons/data-source.svg" alt="" aria-hidden="true" width="30" height="30">
                  <span class="file-copy">
                    @if (file(); as selected) { <strong>{{ safeName(selected.name) }}</strong><small>{{ formatBytes(selected.size) }}</small> }
                    @else { <strong>{{ i18n.t('imports.chooseFile') }}</strong><small>{{ i18n.t('imports.noFile') }}</small> }
                  </span>
                  <span class="picker-action">{{ i18n.t(file() ? 'imports.changeFile' : 'imports.browseFile') }}</span>
                </label>
              </div>
              @if (fileError()) { <p id="import-file-error" class="error inline-error" role="alert">{{ fileError() }}</p> }
            </section>
          </div>
          <footer class="form-actions"><button type="submit" [disabled]="!canSubmit()" [attr.aria-busy]="busy()">{{ i18n.t(busy() ? 'imports.submitting' : 'imports.submit') }}</button></footer>
        </form>

      </div>

      @if (policyLoading()) { <p class="policy-status" role="status">{{ i18n.t('imports.policyLoading') }}</p> }
      @if (policyFailure()) { <div class="result-panel error" role="alert"><strong>{{ i18n.t('imports.policyError') }}</strong>@if(policyFailure()?.correlationId){<p class="technical">{{ i18n.t('imports.correlation') }}: {{ policyFailure()?.correlationId }}</p>}</div> }

      @if (state() !== 'idle') {
        <section class="result-panel result" role="status" aria-live="polite">
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
    :host{display:block;height:100%;min-height:0}.imports-page{--line:color-mix(in srgb,var(--syn-text) 9%,transparent);background:var(--syn-bg-card);border:1px solid var(--line);border-radius:28px;display:flex;flex-direction:column;gap:16px;height:100%;min-height:0;overflow:hidden;padding:clamp(20px,2.5vw,34px)}.sr-only,.file-input{clip:rect(0,0,0,0);clip-path:inset(50%);height:1px;overflow:hidden;position:absolute;white-space:nowrap;width:1px}.import-workspace{display:grid;gap:24px;min-height:0;overflow-x:hidden;overflow-y:auto;padding-right:4px;scrollbar-gutter:stable;width:100%}.workspace-heading{align-items:center;display:flex}.workspace-heading h2,.workspace-heading p{margin:0}.workspace-heading h2{font-size:1.35rem;text-wrap:balance}.workspace-heading p{color:var(--syn-text-secondary);font-size:.88rem;margin-top:4px}.workflow-grid{display:grid;gap:18px;grid-template-columns:minmax(240px,.7fr) minmax(360px,1.3fr)}.workflow-step{border:1px solid var(--line);border-radius:18px;display:flex;flex-direction:column;min-width:0;padding:20px}.workflow-step>header{align-items:flex-start;display:flex;gap:11px;margin-bottom:18px}.workflow-step>header>span{align-items:center;background:var(--syn-primary);border-radius:50%;color:#fff;display:flex;flex:0 0 28px;font-size:.78rem;font-weight:700;height:28px;justify-content:center}.workflow-step h3,.workflow-step p{margin:0}.workflow-step h3{font-size:.95rem}.workflow-step header p{color:var(--syn-text-secondary);font-size:.78rem;line-height:1.45;margin-top:3px}.field-label{font-size:.78rem;font-weight:600;margin-bottom:6px}.source-step select+.field-label{margin-top:16px}.source-step select{background-color:var(--syn-bg-card);color:var(--syn-text);min-height:46px}.file-step{background:color-mix(in srgb,var(--syn-bg) 55%,var(--syn-bg-card))}.file-control{display:flex;flex:1;min-height:150px}.file-picker{align-items:center;border:1px dashed color-mix(in srgb,var(--syn-primary) 38%,var(--syn-border));border-radius:16px;cursor:pointer;display:grid;gap:14px;grid-template-columns:auto minmax(0,1fr) auto;padding:24px;transition:background var(--syn-transition),border-color var(--syn-transition);width:100%}.file-picker:hover,.file-control:focus-within .file-picker{background:var(--syn-primary-light);border-color:var(--syn-primary)}.file-copy{display:grid;min-width:0}.file-copy strong{overflow-wrap:anywhere}.file-copy small{color:var(--syn-text-secondary);font-size:.78rem;margin-top:4px}.picker-action{background:var(--syn-bg-card);border:1px solid var(--syn-border);border-radius:999px;color:var(--syn-primary);font-size:.8rem;font-weight:700;padding:9px 14px;white-space:nowrap}.inline-error{font-size:.8rem;margin:10px 0 0}.form-actions{border-top:1px solid var(--line);display:flex;justify-content:flex-end;margin-top:18px;padding-top:18px}.form-actions button{border-radius:999px;min-width:160px}.trust-panel{background:var(--syn-bg);border-radius:16px;justify-self:center;max-width:58rem;padding:16px 18px;width:fit-content}.trust-panel>header{margin-bottom:13px}.trust-panel h2{font-size:.9rem;margin:0}.trust-grid{display:grid;gap:10px 28px;grid-template-columns:repeat(2,minmax(18rem,1fr))}.trust-item{color:var(--syn-text-secondary);font-size:.76rem;line-height:1.45;min-width:0}.policy-status,.result-panel{width:100%}.policy-status{color:var(--syn-text-secondary);font-size:.82rem;margin:0}.result-panel{background:var(--syn-bg-card);border:1px solid var(--syn-border);border-radius:16px;padding:18px}.result{border-left:4px solid var(--syn-info)}progress{accent-color:var(--syn-primary);inline-size:100%;min-height:1rem}.button-link{display:inline-block;font-weight:700;margin-top:var(--space-3)}
    @media(max-width:54rem){.workflow-grid{grid-template-columns:1fr}.trust-grid{grid-template-columns:1fr}}
    @media(max-width:36rem){.imports-page{border-radius:20px;padding:18px}.trust-panel{width:100%}.trust-grid{grid-template-columns:1fr}.workflow-step{padding:16px}.file-picker{grid-template-columns:auto minmax(0,1fr);padding:18px}.picker-action{grid-column:1/-1;text-align:center}.form-actions button{width:100%}}
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
        if (this.file()) this.fileError.set(this.validate(this.file()));
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
