import { TranslationKey } from '../../shared/i18n/i18n.models';
export const PENDING_PRIORITY_KEYS: Record<string, TranslationKey> = {
  critical: 'pending.priority.critical',
  high: 'pending.priority.high',
  normal: 'pending.priority.normal',
  low: 'pending.priority.low'
};

export const PENDING_STATUS_KEYS: Record<string, TranslationKey> = {
  open: 'pending.status.open',
  resolved: 'pending.status.resolved',
  cancelled: 'pending.status.cancelled'
};
