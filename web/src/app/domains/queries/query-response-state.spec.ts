import { ConsolidatedWorkorder, Lot, OperationalSearchPage, Serial } from './query.models';
import { QUERY_STALE_AFTER_MS, isEntityPartial, isSearchPartial, isStale, isWorkorderPartial } from './query-response-state';

describe('query response states', () => {
  it('marks data older than 24 hours as stale', () => {
    const reference = Date.parse('2026-09-04T12:00:00Z');
    expect(isStale('2026-09-04T12:00:00Z', reference + QUERY_STALE_AFTER_MS)).toBeFalse();
    expect(isStale('2026-09-04T12:00:00Z', reference + QUERY_STALE_AFTER_MS + 1)).toBeTrue();
  });

  it('marks incomplete search and detail relationships as partial', () => {
    const page = searchPage();
    expect(isSearchPartial(page)).toBeFalse();
    expect(isSearchPartial({ ...page, items: [{ ...page.items[0], processing_status: null }] })).toBeTrue();

    const workorder = consolidatedWorkorder();
    expect(isWorkorderPartial(workorder)).toBeFalse();
    expect(isWorkorderPartial({ ...workorder, classifications: [{ ...workorder.classifications[0], data_quality: 'partial' }] })).toBeTrue();

    expect(isEntityPartial(lot())).toBeFalse();
    expect(isEntityPartial({ ...lot(), workorder_number: '' })).toBeTrue();
    expect(isEntityPartial({ ...serial(), container_number: null })).toBeTrue();
  });
});

function searchPage(): OperationalSearchPage {
  return { items: [{ entity_type: 'workorder', identifier: 'WO-001', execution_id: 'exec-1', workorder_number: 'WO-001', lot_number: null, serial_number: null, organization_code: 'ORG', processing_status: 'completed', updated_at: '2026-09-04T12:00:00Z' }], pagination: { page: 1, page_size: 10, total: 1, pages: 1 }, sort: 'updated_desc', entity_type: 'workorder', query: 'WO-001', source: 'synergia.operational', generated_at: '2026-09-04T12:00:00Z' };
}

function consolidatedWorkorder(): ConsolidatedWorkorder {
  return { workorder: { execution_id: 'exec-1', workorder_number: 'WO-001', organization_code: 'ORG', processing_status: 'completed', planned_quantity: 1, produced_quantity: 1, received_quantity: 1, released_quantity: 1, pending_quantity: 0, retained_quantity: 0, partially_released: false, lots: [], serials: [], updated_at: '2026-09-04T12:00:00Z' }, classifications: [{ classification_id: 'c-1', rule_id: 'r-1', state: 'active', entity_type: 'workorder', entity_id: 'WO-001', justification: 'Synthetic', reason: null, data_quality: 'complete' }], pending_items: [], provenance: [] };
}

function lot(): Lot { return { execution_id: 'exec-1', workorder_number: 'WO-001', lot_number: 'LOT-001', serials: [], updated_at: '2026-09-04T12:00:00Z' }; }
function serial(): Serial { return { execution_id: 'exec-1', workorder_number: 'WO-001', lot_number: 'LOT-001', serial_number: 'SER-001', container_number: 'CONT-001', updated_at: '2026-09-04T12:00:00Z' }; }
