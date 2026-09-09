import { TranslationKey } from '../../shared/i18n/i18n.models';
import { ReportCompleteness, ReportState, ReportType } from './report.models';

export const REPORT_TYPE_KEYS: Record<ReportType, TranslationKey> = {
  workorder_consolidated: 'reports.type.workorder',
  oqc_summary: 'reports.type.oqc'
};
export const REPORT_STATE_KEYS: Record<ReportState, TranslationKey> = {
  generating: 'reports.state.generating',
  succeeded: 'reports.state.succeeded',
  failed: 'reports.state.failed',
  cancelled: 'reports.state.cancelled'
};
export const REPORT_COMPLETENESS_KEYS: Record<ReportCompleteness, TranslationKey> = {
  complete: 'reports.completeness.complete',
  partial: 'reports.completeness.partial'
};
export const REPORT_DATA_STATE_KEYS: Record<string, TranslationKey> = {
  pending: 'reports.dataState.pending',
  validated: 'reports.dataState.validated',
  consolidated: 'reports.dataState.consolidated',
  failed: 'reports.dataState.failed',
  approved: 'reports.dataState.approved',
  partially_approved: 'reports.dataState.partiallyApproved',
  rejected: 'reports.dataState.rejected',
  not_applicable: 'reports.dataState.notApplicable'
};
