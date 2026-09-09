import { NotificationItem, NotificationPage } from './notification.models';

export function notification(changes: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id: '77777777-7777-4777-8777-777777777777', type: 'execution.completed', state: 'unread',
    title: 'Processamento concluído', body: 'A execução exec-1 foi concluída.', occurrence_count: 1,
    organization_id: '44444444-4444-4444-8444-444444444444', resource_type: 'execution',
    resource_url: '/executions/exec-1', resource_available: true, template_version: '1.0.0', version: 1,
    first_occurred_at: '2026-09-09T12:00:00Z', last_occurred_at: '2026-09-09T12:00:00Z', read_at: null,
    ...changes
  };
}

export function notificationPage(items: NotificationItem[]): NotificationPage {
  return { items, pagination: { page: 1, page_size: 20, total: items.length, pages: items.length ? 1 : 0 }, sort: 'newest', filter: 'all' };
}
