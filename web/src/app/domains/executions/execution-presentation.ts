import { ParamMap } from '@angular/router';
import { compareInstants, profileInstant } from '../../shared/i18n/profile-time';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { EXECUTION_OUTCOMES, ExecutionAggregate, ExecutionOutcome, ExecutionScopeFilters } from './execution.models';

export const OUTCOME_LABELS: Record<ExecutionOutcome, TranslationKey> = {
  active: 'executions.outcome.active', completed: 'executions.outcome.completed',
  partial: 'executions.outcome.partial', skipped_duplicate: 'executions.outcome.skipped_duplicate',
  failed: 'executions.outcome.failed', cancelled: 'executions.outcome.cancelled', unknown: 'executions.outcome.unknown'
};
export const OUTCOME_COLORS: Record<ExecutionOutcome, string> = {
  active: 'var(--syn-info)', completed: 'var(--syn-success)', partial: 'var(--syn-attention)',
  skipped_duplicate: 'var(--syn-text-secondary)', failed: 'var(--syn-error)',
  cancelled: 'var(--syn-neutral, #68758a)', unknown: 'var(--syn-text-secondary)'
};
export function outcomeLabel(value: string | undefined): TranslationKey {
  return OUTCOME_LABELS[value as ExecutionOutcome] ?? OUTCOME_LABELS.unknown;
}

export function executionStatusLabel(value: string): TranslationKey {
  const labels: Record<string, TranslationKey> = {
    pending: 'executions.status.pending', validating: 'executions.status.validating',
    normalizing: 'executions.status.normalizing', consolidating: 'executions.status.consolidating',
    applying_rules: 'executions.status.applying_rules', reprocessing: 'executions.status.reprocessing',
    completed: 'executions.status.completed', completed_with_errors: 'executions.status.completed_with_errors',
    duplicate: 'executions.status.duplicate', validation_failed: 'executions.status.validation_failed',
    failed: 'executions.status.failed', cancelled: 'executions.status.cancelled'
  };
  return labels[value] ?? OUTCOME_LABELS.unknown;
}

export function legacyLifecycleLabel(value: string): TranslationKey {
  const labels: Record<string, TranslationKey> = { active: 'executions.lifecycle.active', completed: 'executions.lifecycle.completed', partial: 'executions.lifecycle.partial', failed: 'executions.lifecycle.failed' };
  return labels[value] ?? OUTCOME_LABELS.unknown;
}

export function normalizedExecutionFilters(value: ExecutionScopeFilters, timezone: string): ExecutionScopeFilters {
  const dateFrom = profileInstant(value.dateFrom, timezone, 'start');
  const dateTo = profileInstant(value.dateTo, timezone, 'end');
  if (dateFrom && dateTo && compareInstants(dateFrom, dateTo) > 0) throw new RangeError('invalid_period');
  return {
    organizationId: value.organizationId?.trim().toLowerCase() || undefined,
    source: value.source?.trim() || undefined, fileType: value.fileType?.toLowerCase().replace(/^\.+/, '') || undefined,
    dateFrom, dateTo, status: value.status?.trim() || undefined,
    lifecycle: value.lifecycle || undefined, outcome: value.outcome || undefined, executionId: value.executionId?.trim() || undefined
  };
}

export function filtersFromParams(params: ParamMap, timezone: string): ExecutionScopeFilters {
  return normalizedExecutionFilters({
    organizationId: params.get('organization_id') ?? params.get('organization') ?? undefined,
    source: params.get('source') ?? undefined, fileType: params.get('file_type') ?? undefined,
    dateFrom: params.get('date_from') ?? params.get('dateFrom') ?? undefined,
    dateTo: params.get('date_to') ?? params.get('dateTo') ?? undefined,
    status: params.get('status') ?? undefined, lifecycle: params.get('lifecycle') ?? undefined,
    outcome: params.get('outcome') as ExecutionOutcome | null ?? undefined,
    executionId: params.get('execution_id') ?? undefined
  }, timezone);
}

export function filtersFromAggregate(summary: ExecutionAggregate): ExecutionScopeFilters {
  const filters = summary.filters;
  return {
    organizationId: filters.organization_id ?? undefined, source: filters.source ?? undefined,
    fileType: filters.file_type ?? undefined, dateFrom: filters.date_from ?? undefined,
    dateTo: filters.date_to ?? undefined, status: filters.status ?? undefined,
    lifecycle: filters.lifecycle ?? undefined, outcome: filters.outcome ?? undefined,
    executionId: filters.execution_id ?? undefined
  };
}

export function executionUrlParams(filters: ExecutionScopeFilters): Record<string, string | null> {
  return {
    organization_id: filters.organizationId ?? null, source: filters.source ?? null,
    file_type: filters.fileType ?? null, date_from: filters.dateFrom ?? null, date_to: filters.dateTo ?? null,
    status: filters.status ?? null, lifecycle: filters.lifecycle ?? null, outcome: filters.outcome ?? null,
    execution_id: filters.executionId ?? null
  };
}

export function hasExecutionAggregate(summary: ExecutionAggregate | null | undefined): summary is ExecutionAggregate {
  return !!summary && Number.isSafeInteger(summary.total) && summary.total >= 0
    && EXECUTION_OUTCOMES.every(outcome => Number.isSafeInteger(summary.by_outcome?.[outcome]) && summary.by_outcome[outcome] >= 0)
    && EXECUTION_OUTCOMES.reduce((sum, outcome) => sum + summary.by_outcome[outcome], 0) === summary.total;
}
