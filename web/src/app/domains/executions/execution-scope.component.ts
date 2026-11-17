import { Component, inject, input } from '@angular/core';
import { I18nService } from '../../shared/i18n/i18n.service';
import { ExecutionAggregate } from './execution.models';
import { executionStatusLabel, legacyLifecycleLabel, outcomeLabel } from './execution-presentation';

@Component({
  selector: 'syn-execution-scope',
  template: `
    @if (summary(); as current) {
      <details class="execution-scope">
        <summary>{{ i18n.t(current.scope.permission === 'dashboard.read' ? 'executions.scope.dashboard' : 'executions.scope.title') }} · {{ current.scope.organization_ids === null ? i18n.t('executions.scope.global') : i18n.t('executions.scope.count', { count: i18n.formatNumber(current.scope.organization_ids.length) }) }}</summary>
        <dl>
          @if (current.filters.organization_id) { <div><dt>{{ i18n.t('executions.scope.organization') }}</dt><dd class="technical">{{ current.filters.organization_id }}</dd></div> }
          @else if (current.scope.organization_ids) { <div><dt>{{ i18n.t('executions.organization') }}</dt><dd class="technical">{{ current.scope.organization_ids.join(', ') }}</dd></div> }
          <div><dt>{{ i18n.t('executions.scope.period') }}</dt><dd><time [attr.datetime]="current.filters.date_from">{{ date(current.filters.date_from) }}</time> – <time [attr.datetime]="current.filters.date_to">{{ date(current.filters.date_to) }}</time></dd></div>
          @if (current.filters.source) { <div><dt>{{ i18n.t('executions.source') }}</dt><dd>{{ current.filters.source }}</dd></div> }
          @if (current.filters.file_type) { <div><dt>{{ i18n.t('executions.fileType') }}</dt><dd>{{ current.filters.file_type }}</dd></div> }
          @if (current.filters.outcome) { <div><dt>{{ i18n.t('executions.scope.status') }}</dt><dd>{{ i18n.t(label(current.filters.outcome)) }}</dd></div> }
          @if (current.filters.status) { <div><dt>{{ i18n.t('executions.persistedState') }}</dt><dd>{{ i18n.t(status(current.filters.status)) }}</dd></div> }
          @if (current.filters.lifecycle) { <div><dt>{{ i18n.t('executions.publicState') }}</dt><dd>{{ i18n.t(legacy(current.filters.lifecycle)) }}</dd></div> }
          @if (current.filters.execution_id) { <div><dt>{{ i18n.t('executions.id') }}</dt><dd class="technical">{{ current.filters.execution_id }}</dd></div> }
        </dl>
      </details>
    }
  `,
  styles: [`:host{display:block;min-width:0}.execution-scope{border-bottom:1px solid var(--syn-border);padding-block:8px}.execution-scope summary{cursor:pointer;color:var(--syn-text-secondary);font-size:.8rem;min-height:44px;align-content:center;overflow-wrap:anywhere}.execution-scope summary:focus-visible{outline:2px solid var(--syn-link);outline-offset:2px}.execution-scope dl{display:flex;flex-wrap:wrap;gap:10px 24px;margin:0 0 10px}.execution-scope dl>div{min-width:0;max-width:100%}.execution-scope dt{color:var(--syn-text-secondary);font-size:.72rem}.execution-scope dd{margin:3px 0 0;font-size:.8rem;overflow-wrap:anywhere}`]
})
export class ExecutionScopeComponent {
  readonly summary = input<ExecutionAggregate | null | undefined>();
  readonly i18n = inject(I18nService);
  readonly label = outcomeLabel;
  readonly status = executionStatusLabel;
  readonly legacy = legacyLifecycleLabel;
  date(value: string | null): string {
    return value ? this.i18n.formatDate(value, { dateStyle: 'short', timeStyle: 'short' }) : this.i18n.t('executions.scope.unbounded');
  }
}
