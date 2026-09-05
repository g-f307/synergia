import { pendingItem, pendingPage } from './pending.fixtures';
import { pendingIsPartial, pendingIsStale, pendingKind, pendingPageIsPartial } from './pending-state';

describe('pending response states', () => {
  it('distinguishes operational categories without changing stable rule codes', () => {
    expect(pendingKind(pendingItem({ category: 'pre_release_pending' }))).toBe('pre-release');
    expect(pendingKind(pendingItem({ category: 'post_release_hold' }))).toBe('post-release');
    expect(pendingKind(pendingItem({ category: 'processing_failure' }))).toBe('technical');
    expect(pendingKind(pendingItem({ category: 'partial_release' }))).toBe('partial');
  });

  it('identifies incomplete and outdated records', () => {
    const complete = pendingItem();
    expect(pendingIsPartial(complete)).toBeFalse();
    expect(pendingPageIsPartial(pendingPage([pendingItem({ rule_catalog_version: null })]))).toBeTrue();
    expect(pendingIsStale('2026-09-01T00:00:00Z', Date.parse('2026-09-02T00:00:00Z'))).toBeFalse();
    expect(pendingIsStale('2026-09-01T00:00:00Z', Date.parse('2026-09-02T00:00:00Z') + 1)).toBeTrue();
  });
});
