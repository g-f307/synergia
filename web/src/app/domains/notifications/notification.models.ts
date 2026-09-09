export type NotificationState = 'unread' | 'read';
export type NotificationFilter = 'all' | NotificationState;
export type NotificationSort = 'newest' | 'oldest';

export interface NotificationItem {
  id: string;
  type: string;
  state: NotificationState;
  title: string;
  body: string;
  occurrence_count: number;
  organization_id: string;
  resource_type: 'execution' | 'pending' | 'report';
  resource_url: string | null;
  resource_available: boolean;
  template_version: string;
  version: number;
  first_occurred_at: string;
  last_occurred_at: string;
  read_at: string | null;
}

export interface NotificationPage {
  items: NotificationItem[];
  pagination: { page: number; page_size: number; total: number; pages: number };
  sort: NotificationSort;
  filter: NotificationFilter;
}
