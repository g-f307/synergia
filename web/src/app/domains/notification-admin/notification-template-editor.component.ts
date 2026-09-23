import { KeyValuePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import {
  NotificationTemplateChannel, NotificationTemplateLocale, NotificationTemplatePolicy,
  NotificationTemplatePreview, NotificationTemplateRevision, NotificationTemplateState
} from './notification-template.models';
import { NotificationTemplateService } from './notification-template.service';

const CHANNEL_KEYS: Record<NotificationTemplateChannel, TranslationKey> = {
  in_app: 'notificationAdmin.channel.inApp',
  email: 'notificationAdmin.channel.email'
};
const DELIVERY_KEYS: Record<NotificationTemplatePolicy['external_delivery'], TranslationKey> = {
  disabled: 'notificationAdmin.delivery.disabled',
  local_capture: 'notificationAdmin.delivery.localCapture',
  unavailable: 'notificationAdmin.delivery.unavailable'
};

@Component({
  selector: 'syn-notification-template-editor',
  imports: [FormsModule, KeyValuePipe, RouterLink],
  templateUrl: './notification-template-editor.component.html',
  styleUrls: ['../admin/admin.component.css', './notification-template.component.css']
})
export class NotificationTemplateEditorComponent {
  readonly i18n = inject(I18nService);
  private readonly api = inject(NotificationTemplateService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly id = this.route.snapshot.paramMap.get('templateId');
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly policy = signal<NotificationTemplatePolicy | null>(null);
  readonly item = signal<NotificationTemplateRevision | null>(null);
  readonly history = signal<NotificationTemplateRevision[]>([]);
  readonly historyPage = signal(1);
  readonly historyPages = signal(0);
  readonly preview = signal<NotificationTemplatePreview | null>(null);
  readonly failure = signal<ApiFailure | null>(null);
  readonly formError = signal<TranslationKey | null>(null);
  eventType = '';
  channel: NotificationTemplateChannel = 'in_app';
  locale: NotificationTemplateLocale = 'pt-BR';
  titleTemplate = '';
  bodyTemplate = '';
  reason = '';

  constructor() { this.reload(); }

  reload(): void {
    this.loading.set(true); this.failure.set(null); this.preview.set(null);
    if (!this.id) {
      this.api.policy().subscribe({
        next: (policy) => {
          this.policy.set(policy); this.eventType = policy.events[0]?.notification_type ?? '';
          this.loading.set(false);
        },
        error: (failure: ApiFailure) => this.failedLoad(failure)
      });
      return;
    }
    forkJoin({ policy: this.api.policy(), item: this.api.get(this.id) }).subscribe({
      next: ({ policy, item }) => {
        this.policy.set(policy); this.accept(item); this.loading.set(false); this.loadHistory(item);
      },
      error: (failure: ApiFailure) => this.failedLoad(failure)
    });
  }

  save(event: Event): void {
    event.preventDefault(); this.formError.set(null); this.failure.set(null); this.preview.set(null);
    if (!this.eventType || !this.titleTemplate.trim() || !this.bodyTemplate.trim() || this.reason.trim().length < 3) {
      this.formError.set('notificationAdmin.required'); return;
    }
    this.busy.set(true);
    const current = this.item();
    const request = current
      ? this.api.update(current.id, {
        row_version: current.row_version, title_template: this.titleTemplate.trim(),
        body_template: this.bodyTemplate.trim(), reason: this.reason.trim()
      })
      : this.api.create({
        notification_type: this.eventType, channel: this.channel, locale: this.locale,
        title_template: this.titleTemplate.trim(), body_template: this.bodyTemplate.trim(),
        reason: this.reason.trim()
      });
    request.subscribe({
      next: (item) => {
        this.busy.set(false); this.reason = '';
        if (!current) void this.router.navigate(['/admin/notification-templates', item.id]);
        else { this.accept(item); this.loadHistory(item); }
      },
      error: (failure: ApiFailure) => this.failedMutation(failure)
    });
  }

  requestPreview(): void {
    const current = this.item();
    if (!current || this.busy()) return;
    this.busy.set(true); this.failure.set(null);
    this.api.preview(current.id).subscribe({
      next: (preview) => { this.preview.set(preview); this.busy.set(false); },
      error: (failure: ApiFailure) => this.failedMutation(failure)
    });
  }

  publish(): void {
    const current = this.item();
    if (!current || current.state !== 'draft' || !this.validReason()) return;
    if (!window.confirm(this.i18n.t('notificationAdmin.confirmPublish'))) return;
    this.transition('publish');
  }

  deactivate(): void {
    const current = this.item();
    if (!current || current.state !== 'active' || !this.validReason()) return;
    if (!window.confirm(this.i18n.t('notificationAdmin.confirmDeactivate'))) return;
    this.transition('deactivate');
  }

  selectedPlaceholders(): string[] {
    return this.item()?.allowed_placeholders
      ?? this.policy()?.events.find((item) => item.notification_type === this.eventType)?.allowed_placeholders
      ?? [];
  }
  editable(): boolean { return !this.item() || this.item()?.state === 'draft'; }
  stateKey(state: NotificationTemplateState): TranslationKey {
    return `notificationAdmin.state.${state}` as TranslationKey;
  }
  channelKey(channel: NotificationTemplateChannel): TranslationKey {
    return CHANNEL_KEYS[channel];
  }
  deliveryKey(): TranslationKey {
    return DELIVERY_KEYS[this.policy()?.external_delivery ?? 'unavailable'];
  }
  changeHistoryPage(page: number): void {
    const current = this.item();
    if (!current || page < 1 || page > this.historyPages()) return;
    this.loadHistory(current, page);
  }
  failureKey(): TranslationKey {
    if (this.failure()?.kind === 'forbidden') return 'notificationAdmin.forbidden';
    if (this.failure()?.kind === 'conflict') return 'notificationAdmin.conflict';
    if (this.failure()?.kind === 'validation') return 'notificationAdmin.validation';
    if (this.failure()?.kind === 'not-found') return 'notificationAdmin.notFound';
    if (this.failure()?.kind === 'unavailable') return 'notificationAdmin.unavailable';
    return 'notificationAdmin.error';
  }

  private transition(action: 'publish' | 'deactivate'): void {
    const current = this.item()!;
    this.busy.set(true); this.failure.set(null); this.preview.set(null);
    const request = action === 'publish'
      ? this.api.publish(current.id, current.row_version, this.reason.trim())
      : this.api.deactivate(current.id, current.row_version, this.reason.trim());
    request.subscribe({
      next: (item) => { this.busy.set(false); this.reason = ''; this.accept(item); this.loadHistory(item); },
      error: (failure: ApiFailure) => this.failedMutation(failure)
    });
  }
  private validReason(): boolean {
    this.formError.set(null);
    if (this.reason.trim().length >= 3) return true;
    this.formError.set('notificationAdmin.reasonRequired'); return false;
  }
  private accept(item: NotificationTemplateRevision): void {
    this.item.set(item); this.eventType = item.notification_type; this.channel = item.channel;
    this.locale = item.locale; this.titleTemplate = item.title_template; this.bodyTemplate = item.body_template;
  }
  private loadHistory(item: NotificationTemplateRevision, page = 1): void {
    this.api.list({
      notification_type: item.notification_type, channel: item.channel,
      locale: item.locale, page, page_size: 100, sort: 'newest'
    }).subscribe({
      next: (result) => {
        this.history.set(result.items);
        this.historyPage.set(result.page);
        this.historyPages.set(result.pages);
      },
      error: (failure: ApiFailure) => this.failure.set(failure)
    });
  }
  private failedLoad(failure: ApiFailure): void { this.failure.set(failure); this.loading.set(false); }
  private failedMutation(failure: ApiFailure): void { this.failure.set(failure); this.busy.set(false); }
}
