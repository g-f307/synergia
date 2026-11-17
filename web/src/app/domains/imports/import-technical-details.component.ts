import { Component, effect, inject, input, signal } from '@angular/core';

import { I18nService } from '../../shared/i18n/i18n.service';

@Component({
  selector: 'syn-import-technical-details',
  template: `
    <details>
      <summary>{{ i18n.t('imports.technical.title') }}</summary>
      <dl>
        @if (code()) { <div><dt>{{ i18n.t('imports.technical.code') }}</dt><dd class="technical">{{ code() }}</dd></div> }
        @if (status(); as httpStatus) { <div><dt>{{ i18n.t('imports.technical.httpStatus') }}</dt><dd>{{ httpStatus }}</dd></div> }
      </dl>
      @if (correlationId(); as correlation) {
        <label>{{ i18n.t('imports.correlation') }}
          <input class="technical" readonly [value]="correlation" (focus)="$any($event.target).select()" #identifier>
        </label>
        <button type="button" class="secondary" (click)="copy(identifier)">{{ i18n.t('imports.technical.copy') }}</button>
        @if (copyResult(); as result) { <p role="status">{{ i18n.t(result === 'copied' ? 'imports.technical.copied' : 'imports.technical.copyManual') }}</p> }
      }
    </details>
  `,
  styles: [`
    :host{display:block;margin-top:var(--space-3);min-width:0}
    details{overflow-wrap:anywhere}summary{cursor:pointer;min-height:44px;align-content:center;color:var(--syn-link)}
    dl{display:flex;flex-wrap:wrap;gap:var(--space-4);margin:var(--space-2) 0}dt{color:var(--color-muted)}dd{margin:0}
    label{display:grid;gap:var(--space-2);max-width:30rem}input{min-width:0;width:100%}button{margin-top:var(--space-2)}
    p{margin:var(--space-2) 0 0}
  `]
})
export class ImportTechnicalDetailsComponent {
  readonly i18n = inject(I18nService);
  readonly code = input<string | null>(null);
  readonly status = input<number | null>(null);
  readonly correlationId = input<string | null>(null);
  readonly copyResult = signal<'copied' | 'manual' | null>(null);

  constructor() { effect(() => { this.correlationId(); this.copyResult.set(null); }); }

  async copy(identifier: HTMLInputElement): Promise<void> {
    const correlation = this.correlationId();
    if (!correlation) return;
    this.copyResult.set(null);
    try {
      await navigator.clipboard.writeText(correlation);
      if (correlation === this.correlationId()) this.copyResult.set('copied');
    } catch {
      identifier.focus();
      identifier.select();
      if (correlation === this.correlationId()) this.copyResult.set('manual');
    }
  }
}
