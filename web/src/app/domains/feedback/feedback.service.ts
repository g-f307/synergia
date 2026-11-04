import { Injectable, inject } from '@angular/core';
import { ApiClient } from '../../shared/api/api-client.service';
import { ApiFailure } from '../../shared/api/api-error';
import { TranslationKey } from '../../shared/i18n/i18n.models';

export type FeedbackState = 'received' | 'under_review' | 'planned' | 'resolved' | 'discarded';
export type FeedbackKind = 'bug' | 'suggestion';
export interface FeedbackEvent { id: number; actor_user_id: string; from_state: FeedbackState | null; to_state: FeedbackState; version: number; reason: string | null; occurred_at: string; }
export interface FeedbackItem { id: string; protocol: string; organization_id: string; author_user_id: string; kind: FeedbackKind; title: string; description: string; expected_result: string | null; observed_result: string | null; source_route: string; state: FeedbackState; version: number; created_at: string; updated_at: string; history: FeedbackEvent[]; allowed_transitions: FeedbackState[]; }
export interface FeedbackPolicy { can_create: boolean; organization: { id: string; display_name: string } | null; organization_issue: 'missing' | 'ambiguous' | null; sources: { id: string; route: string }[]; }
export interface FeedbackPayload { kind: FeedbackKind; title: string; description: string; source_id: string; expected_result?: string; observed_result?: string; }
export interface FeedbackPage { items: FeedbackItem[]; pagination: { page: number; pages: number; total: number }; }
export const feedbackStates: FeedbackState[] = ['received', 'under_review', 'planned', 'resolved', 'discarded'];

@Injectable({ providedIn: 'root' })
export class FeedbackService {
  private readonly api = inject(ApiClient);
  policy() { return this.api.get<FeedbackPolicy>('feedback/policy'); }
  create(payload: FeedbackPayload) { return this.api.post<FeedbackItem>('feedback', payload); }
  list(triage: boolean, page: number, filters: Record<string, string>) { return this.api.get<FeedbackPage>(triage ? 'feedback/triage' : 'feedback', { page, pageSize: 20, sort: 'newest', filters }); }
  detail(triage: boolean, id: string) { return this.api.get<FeedbackItem>((triage ? 'feedback/triage/' : 'feedback/') + encodeURIComponent(id)); }
  transition(item: FeedbackItem, state: FeedbackState, reason: string) { return this.api.patch<FeedbackItem>('feedback/triage/' + item.id, { version: item.version, state, reason: reason.trim() || null }); }
  stateKey(state: FeedbackState): TranslationKey { return { received: 'feedback.state.received', under_review: 'feedback.state.under_review', planned: 'feedback.state.planned', resolved: 'feedback.state.resolved', discarded: 'feedback.state.discarded' }[state] as TranslationKey; }
  errorKey(failure: ApiFailure): TranslationKey {
    if (failure.code === 'feedback_organization_missing') return 'feedback.organizationMissing';
    if (failure.code === 'feedback_organization_ambiguous') return 'feedback.organizationAmbiguous';
    if (failure.status === 409) return 'feedback.conflict';
    if (failure.status === 403) return 'feedback.forbidden';
    if (failure.status === 404) return 'feedback.notFound';
    if (failure.status === 422) return 'feedback.validation';
    if (failure.status === 429) return 'feedback.rateLimit';
    return 'feedback.unavailable';
  }
}
