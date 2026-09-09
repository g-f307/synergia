import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { notification, notificationPage } from './notification.fixtures';
import { NotificationService } from './notification.service';

describe('NotificationService', () => {
  let service: NotificationService; let http: HttpTestingController;
  beforeEach(() => { TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] }); service = TestBed.inject(NotificationService); http = TestBed.inject(HttpTestingController); });
  afterEach(() => http.verify());
  it('sends stable feed filters and pagination', () => { service.list('unread', 'oldest', 2, 10).subscribe(); const request = http.expectOne((candidate) => candidate.url === `${environment.apiUrl}/notifications`); expect(request.request.params.get('filter')).toBe('unread'); expect(request.request.params.get('sort')).toBe('oldest'); expect(request.request.params.get('page')).toBe('2'); expect(request.request.params.get('page_size')).toBe('10'); request.flush(notificationPage([])); });
  it('keeps unread count synchronized after persistent read actions', () => { service.unreadCount.set(2); const item = notification(); service.markRead(item).subscribe(); const read = http.expectOne(`${environment.apiUrl}/notifications/${item.id}/read`); expect(read.request.method).toBe('PATCH'); expect(read.request.body).toEqual({ version: 1 }); read.flush(notification({ state: 'read', version: 2, read_at: '2026-09-09T12:10:00Z' })); expect(service.unreadCount()).toBe(1); service.markAllRead().subscribe(); http.expectOne(`${environment.apiUrl}/notifications/read-all`).flush({ count: 1 }); expect(service.unreadCount()).toBe(0); });
  it('does not restore a previous session count after reset', () => { service.refreshUnreadCount(); const request = http.expectOne(`${environment.apiUrl}/notifications/unread-count`); service.reset(); request.flush({ count: 8 }); expect(service.unreadCount()).toBe(0); });
});
