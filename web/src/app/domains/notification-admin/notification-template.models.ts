export type NotificationTemplateChannel = 'in_app' | 'email';
export type NotificationTemplateLocale = 'pt-BR' | 'en-US';
export type NotificationTemplateState = 'draft' | 'active' | 'inactive';

export interface NotificationEventPolicy {
  notification_type: string;
  required_permission: string;
  resource_type: string;
  allowed_placeholders: string[];
}

export interface NotificationTemplatePolicy {
  events: NotificationEventPolicy[];
  channels: NotificationTemplateChannel[];
  locales: NotificationTemplateLocale[];
  external_delivery: 'disabled' | 'local_capture' | 'unavailable';
  external_delivery_corporate: false;
}

export interface NotificationTemplateRevision {
  id: string;
  notification_type: string;
  channel: NotificationTemplateChannel;
  locale: NotificationTemplateLocale;
  version_number: number;
  version_label: string;
  state: NotificationTemplateState;
  title_template: string;
  body_template: string;
  allowed_placeholders: string[];
  row_version: number;
  created_by_user_id: string | null;
  created_reason: string;
  created_at: string;
  updated_by_user_id: string | null;
  updated_reason: string | null;
  updated_at: string;
  published_by_user_id: string | null;
  published_reason: string | null;
  published_at: string | null;
  deactivated_by_user_id: string | null;
  deactivated_reason: string | null;
  deactivated_at: string | null;
}

export interface NotificationTemplatePage {
  items: NotificationTemplateRevision[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
  sort: 'newest' | 'oldest';
}

export interface NotificationTemplatePreview {
  title: string;
  body: string;
  sample_data: Record<string, string>;
  synthetic: true;
}
