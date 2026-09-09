import { ReportDetail, ReportPage, ReportPolicy, ReportVersion } from './report.models';

export function reportVersion(changes: Partial<ReportVersion> = {}): ReportVersion {
  return {
    report_id: '11111111-1111-4111-8111-111111111111', version_id: '22222222-2222-4222-8222-222222222222', version: 1,
    report_type: 'workorder_consolidated', state: 'succeeded', completeness: 'complete', organization_id: '44444444-4444-4444-8444-444444444444', execution_id: 'exec-1',
    requested_by_user_id: '00000000-0000-4000-8000-000000000001', requested_by_display_name: 'Synthetic User', reference_at: '2026-09-08T12:00:00Z', filters: {}, schema_version: '1.1.0', created_at: '2026-09-08T12:01:00Z', completed_at: '2026-09-08T12:02:00Z', failure_code: null, failure_message: null, cancellation_reason: null, ...changes
  };
}

export function reportDetail(changes: Partial<ReportDetail> = {}): ReportDetail {
  return {
    ...reportVersion(),
    data: { kind: 'workorder_consolidated', count: 1, workorders: [{ workorder_number: 'WO-001', organization_code: 'ORG-001', processing_status: 'consolidated', planned_quantity: null, produced_quantity: 0, received_quantity: 8, released_quantity: 4, pending_quantity: 4, retained_quantity: null, partially_released: true, lots: ['LOT-001'], serial_count: 2, open_pending_count: 1 }] },
    ...changes
  };
}

export function reportPage(items: ReportVersion[]): ReportPage { return { items, pagination: { page: 1, page_size: 25, total: items.length, pages: items.length ? 1 : 0 }, sort: 'newest' }; }

export function reportPolicy(): ReportPolicy {
  const organization = { id: '44444444-4444-4444-8444-444444444444', organization_code: 'ORG-001', display_name: 'Organization 001' };
  return { report_types: [{ report_type: 'workorder_consolidated', allowed_states: ['pending', 'consolidated'], allowed_filters: ['state', 'workorder_number'] }, { report_type: 'oqc_summary', allowed_states: ['pending', 'approved'], allowed_filters: ['state', 'lot_number', 'priority'] }], export_formats: ['csv', 'json'], read_organizations: [organization], generation_organizations: [organization], stale_after_seconds: 900 };
}
