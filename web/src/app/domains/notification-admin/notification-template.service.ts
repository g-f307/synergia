import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';

import { environment } from '../../../environments/environment';
import {
  NotificationTemplateChannel, NotificationTemplateLocale, NotificationTemplatePage,
  NotificationTemplatePolicy, NotificationTemplatePreview, NotificationTemplateRevision,
  NotificationTemplateState
} from './notification-template.models';

@Injectable({ providedIn: 'root' })
export class NotificationTemplateService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/admin/notification-templates`;

  policy() { return this.http.get<NotificationTemplatePolicy>(`${this.base}/policy`); }
  list(filters: {
    notification_type?: string;
    channel?: NotificationTemplateChannel;
    locale?: NotificationTemplateLocale;
    state?: NotificationTemplateState;
    sort?: 'newest' | 'oldest';
    page?: number;
    page_size?: number;
  } = {}) {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== '') params = params.set(key, String(value));
    }
    return this.http.get<NotificationTemplatePage>(this.base, { params });
  }
  get(id: string) {
    return this.http.get<NotificationTemplateRevision>(`${this.base}/${encodeURIComponent(id)}`);
  }
  create(payload: {
    notification_type: string;
    channel: NotificationTemplateChannel;
    locale: NotificationTemplateLocale;
    title_template: string;
    body_template: string;
    reason: string;
  }) { return this.http.post<NotificationTemplateRevision>(`${this.base}/drafts`, payload); }
  update(id: string, payload: {
    row_version: number;
    title_template: string;
    body_template: string;
    reason: string;
  }) { return this.http.patch<NotificationTemplateRevision>(`${this.base}/${encodeURIComponent(id)}`, payload); }
  preview(id: string) {
    return this.http.post<NotificationTemplatePreview>(`${this.base}/${encodeURIComponent(id)}/preview`, {});
  }
  publish(id: string, rowVersion: number, reason: string) {
    return this.http.post<NotificationTemplateRevision>(`${this.base}/${encodeURIComponent(id)}/publish`, {
      row_version: rowVersion, reason
    });
  }
  deactivate(id: string, rowVersion: number, reason: string) {
    return this.http.post<NotificationTemplateRevision>(`${this.base}/${encodeURIComponent(id)}/deactivate`, {
      row_version: rowVersion, reason
    });
  }
}
