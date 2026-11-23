import { ParamMap } from '@angular/router';

import { compareInstants, profileInstant } from '../../shared/i18n/profile-time';
import { WorkorderSelection } from './query.models';

export function normalizeWorkorderSelection(value: WorkorderSelection, timezone: string): WorkorderSelection {
  const startedFrom = profileInstant(value.startedFrom, timezone, 'start');
  const startedTo = profileInstant(value.startedTo, timezone, 'end');
  if (startedFrom && startedTo && compareInstants(startedFrom, startedTo) > 0) throw new RangeError('invalid_period');
  return {
    organizationId: value.organizationId?.trim().toLowerCase() || undefined,
    executionId: value.executionId?.trim() || undefined,
    startedFrom, startedTo
  };
}

export function workorderSelectionFromParams(params: ParamMap, timezone: string): WorkorderSelection {
  return normalizeWorkorderSelection({
    organizationId: params.get('organization_id') ?? undefined,
    executionId: params.get('execution_id') ?? undefined,
    startedFrom: params.get('started_from') ?? undefined,
    startedTo: params.get('started_to') ?? undefined
  }, timezone);
}

export function workorderSelectionParams(value: WorkorderSelection): Record<string, string | undefined> {
  return {
    organization_id: value.organizationId, execution_id: value.executionId,
    started_from: value.startedFrom, started_to: value.startedTo
  };
}
