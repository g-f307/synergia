import { ApiFailure } from '../../shared/api/api-error';
import { TranslationKey } from '../../shared/i18n/i18n.models';

export function adminFailureKey(failure: ApiFailure | null): TranslationKey {
  if (!failure) return 'adminUi.error';
  if (failure.kind === 'forbidden') return 'adminUi.forbidden';
  if (failure.kind === 'not-found') return 'adminUi.notFound';
  if (failure.kind === 'conflict') return failure.code === 'last_active_admin' ? 'adminUi.lastAdmin' : 'adminUi.conflict';
  if (failure.kind === 'validation') return 'adminUi.validation';
  if (failure.kind === 'unavailable') return 'adminUi.unavailable';
  return 'adminUi.error';
}

export function positivePage(value: string | null): number {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 1;
}
