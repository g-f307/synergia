import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import {
  NotificationTemplateChannel, NotificationTemplateLocale, NotificationTemplatePage,
  NotificationTemplatePolicy, NotificationTemplateState
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
  selector: 'syn-notification-template-list',
  imports: [FormsModule, RouterLink],
  templateUrl: './notification-template-list.component.html',
  styleUrls: ['../admin/admin.component.css', './notification-template.component.css']
})
export class NotificationTemplateListComponent {
  readonly i18n = inject(I18nService);
  private readonly api = inject(NotificationTemplateService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly loading = signal(true);
  readonly policy = signal<NotificationTemplatePolicy | null>(null);
  readonly result = signal<NotificationTemplatePage | null>(null);
  readonly failure = signal<ApiFailure | null>(null);
  event = this.route.snapshot.queryParamMap.get('event') ?? '';
  channel = (this.route.snapshot.queryParamMap.get('channel') ?? '') as NotificationTemplateChannel | '';
  locale = (this.route.snapshot.queryParamMap.get('locale') ?? '') as NotificationTemplateLocale | '';
  state = (this.route.snapshot.queryParamMap.get('state') ?? '') as NotificationTemplateState | '';

  constructor() { this.load(); }

  load(): void {
    this.loading.set(true); this.failure.set(null);
    const page = Number(this.route.snapshot.queryParamMap.get('page')) || 1;
    forkJoin({
      policy: this.api.policy(),
      result: this.api.list({
        notification_type: this.event || undefined,
        channel: this.channel || undefined,
        locale: this.locale || undefined,
        state: this.state || undefined,
        page
      })
    }).subscribe({
      next: ({ policy, result }) => {
        this.policy.set(policy); this.result.set(result); this.loading.set(false);
      },
      error: (failure: ApiFailure) => { this.failure.set(failure); this.loading.set(false); }
    });
  }

  apply(event: Event): void {
    event.preventDefault();
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        event: this.event || null,
        channel: this.channel || null,
        locale: this.locale || null,
        state: this.state || null,
        page: null
      }
    }).then(() => this.load());
  }

  changePage(page: number): void {
    void this.router.navigate([], {
      relativeTo: this.route, queryParams: { page }, queryParamsHandling: 'merge'
    }).then(() => this.load());
  }

  failureKey(): TranslationKey {
    if (this.failure()?.kind === 'forbidden') return 'notificationAdmin.forbidden';
    if (this.failure()?.kind === 'unavailable') return 'notificationAdmin.unavailable';
    return 'notificationAdmin.error';
  }
  stateKey(state: NotificationTemplateState): TranslationKey {
    return `notificationAdmin.state.${state}` as TranslationKey;
  }
  channelKey(channel: NotificationTemplateChannel): TranslationKey {
    return CHANNEL_KEYS[channel];
  }
  deliveryKey(): TranslationKey {
    return DELIVERY_KEYS[this.policy()?.external_delivery ?? 'unavailable'];
  }
}
