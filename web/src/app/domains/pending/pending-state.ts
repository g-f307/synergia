import { PendingItem, PendingKind, PendingPage } from './pending.models';

const STALE_AFTER_MS = 24 * 60 * 60 * 1000;
const PRE_RELEASE = new Set(['pre_release_pending', 'oqc_pending']);
const POST_RELEASE = new Set(['post_release_hold', 'oqc_hold', 'long_term_hold', 'ship_block']);
const TECHNICAL = new Set(['processing_failure', 'source_divergence', 'missing_reason']);

export function pendingKind(item: Pick<PendingItem, 'category'>): PendingKind {
  if (PRE_RELEASE.has(item.category)) return 'pre-release';
  if (POST_RELEASE.has(item.category)) return 'post-release';
  if (TECHNICAL.has(item.category)) return 'technical';
  if (item.category === 'partial_release') return 'partial';
  return 'operational';
}

export function pendingIsPartial(item: PendingItem): boolean {
  return !item.rule_id || !item.rule_catalog_version || !item.responsible_area;
}

export function pendingPageIsPartial(page: PendingPage): boolean {
  return page.items.some(pendingIsPartial);
}

export function pendingIsStale(timestamp: string, now = Date.now()): boolean {
  const reference = Date.parse(timestamp);
  return Number.isFinite(reference) && now - reference > STALE_AFTER_MS;
}
