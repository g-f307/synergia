import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, UrlTree, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject, Subject, of, throwError } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { NotificationCenterComponent } from './notification-center.component';
import { notification, notificationPage } from './notification.fixtures';
import { NotificationPage } from './notification.models';
import { NotificationService } from './notification.service';

describe('NotificationCenterComponent', () => {
  let fixture: ComponentFixture<NotificationCenterComponent>; let response: Subject<NotificationPage>; let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>; let router: jasmine.SpyObj<Router>; let list: jasmine.Spy; let markRead: jasmine.Spy; let markAllRead: jasmine.Spy;
  beforeEach(async () => {
    response = new Subject(); params = new BehaviorSubject(convertToParamMap({ filter: 'unread', sort: 'oldest', page: '2', pageSize: '10' }));
    router = jasmine.createSpyObj<Router>('Router', ['navigate', 'createUrlTree', 'serializeUrl'], { events: new Subject(), url: '/notifications' }); router.navigate.and.resolveTo(true); router.createUrlTree.and.returnValue({} as UrlTree); router.serializeUrl.and.returnValue('/executions/exec-1');
    list = jasmine.createSpy().and.returnValue(response.asObservable()); markRead = jasmine.createSpy().and.callFake((item) => of({ ...item, state: 'read', version: item.version + 1, read_at: '2026-09-09T12:10:00Z' })); markAllRead = jasmine.createSpy().and.returnValue(of({ count: 1 }));
    await TestBed.configureTestingModule({ imports: [NotificationCenterComponent], providers: [provideRouter([]), { provide: Router, useValue: router }, { provide: ActivatedRoute, useValue: { queryParamMap: params.asObservable() } }, { provide: NotificationService, useValue: { unreadCount: signal(1), list, refreshUnreadCount: jasmine.createSpy(), markRead, markAllRead } }] }).compileComponents();
    fixture = TestBed.createComponent(NotificationCenterComponent); fixture.detectChanges();
  });
  it('renders unread, consolidated and inaccessible resources safely', () => { response.next(notificationPage([notification({ occurrence_count: 3 }), notification({ id: '88888888-8888-4888-8888-888888888888', resource_url: null, resource_available: false })])); fixture.detectChanges(); const text = fixture.nativeElement.textContent as string; expect(text).toContain('Não lida'); expect(text).toContain('3 ocorrências'); expect(text).toContain('Recurso removido ou inacessível'); expect(fixture.nativeElement.querySelectorAll('.notification-list a').length).toBe(1); });
  it('marks one and all notifications through persistent actions', () => { const item = notification(); response.next(notificationPage([item])); fixture.detectChanges(); fixture.componentInstance.markAllRead(); expect(markAllRead).toHaveBeenCalled(); response.next(notificationPage([item])); fixture.componentInstance.markRead(item); expect(markRead).toHaveBeenCalledWith(item); });
  it('preserves filters and ordering in the URL', () => { fixture.componentInstance.changePage(3); expect(router.navigate).toHaveBeenCalledWith([], { relativeTo: jasmine.anything(), queryParams: { filter: 'unread', sort: 'oldest', page: 3, pageSize: 10 } }); });
  it('uses English for the same notification journey', () => { TestBed.inject(I18nService).configure('en-US'); response.next(notificationPage([])); fixture.detectChanges(); expect(fixture.nativeElement.textContent).toContain('No notifications found'); });
  it('distinguishes forbidden access from temporary unavailability', () => { fixture.destroy(); list.and.returnValue(throwError(() => ({ kind: 'forbidden', status: 403, code: 'access_denied', message: 'safe', correlationId: 'notification-403', fields: [] } as ApiFailure))); fixture = TestBed.createComponent(NotificationCenterComponent); fixture.detectChanges(); expect(fixture.nativeElement.querySelector('[data-state="forbidden"]')).not.toBeNull(); expect(fixture.nativeElement.textContent).toContain('notification-403'); });
});
