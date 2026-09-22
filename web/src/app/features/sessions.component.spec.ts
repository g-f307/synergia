import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ActiveSession } from '../core/session.models';
import { SessionService } from '../core/session.service';
import { SessionsComponent } from './sessions.component';

const current: ActiveSession = {
  id: '11111111-1111-4111-8111-111111111111',
  current: true,
  device: 'Chrome / Windows',
  created_at: '2026-09-01T12:00:00Z',
  last_used_at: '2026-09-02T12:00:00Z',
  expires_at: '2026-09-03T12:00:00Z'
};
const other: ActiveSession = { ...current, id: '22222222-2222-4222-8222-222222222222', current: false };

describe('SessionsComponent', () => {
  const session = {
    listSessions: jasmine.createSpy('listSessions'),
    revokeSession: jasmine.createSpy('revokeSession'),
    revokeOtherSessions: jasmine.createSpy('revokeOtherSessions')
  };

  beforeEach(async () => {
    session.listSessions.and.returnValue(of([current, other]));
    session.revokeSession.and.returnValue(of(undefined));
    session.revokeOtherSessions.and.returnValue(of(1));
    session.revokeSession.calls.reset();
    session.revokeOtherSessions.calls.reset();
    await TestBed.configureTestingModule({
      imports: [SessionsComponent],
      providers: [{ provide: SessionService, useValue: session }]
    }).compileComponents();
  });

  it('lists safe active session metadata and identifies the current one', () => {
    const fixture = TestBed.createComponent(SessionsComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Chrome / Windows');
    expect(fixture.nativeElement.textContent).toContain('Sessão atual');
    expect(fixture.nativeElement.querySelectorAll('.session-list li').length).toBe(2);
  });

  it('requires confirmation before revoking one or all other sessions', () => {
    const fixture = TestBed.createComponent(SessionsComponent);
    fixture.detectChanges();
    const confirmation = spyOn(window, 'confirm').and.returnValue(false);
    fixture.componentInstance.revoke(other);
    fixture.componentInstance.revokeOthers();
    expect(session.revokeSession).not.toHaveBeenCalled();
    expect(session.revokeOtherSessions).not.toHaveBeenCalled();

    confirmation.and.returnValue(true);
    fixture.componentInstance.revoke(other);
    expect(session.revokeSession).toHaveBeenCalledWith(other);
    expect(fixture.componentInstance.sessions()).toEqual([current]);
    fixture.componentInstance.revokeOthers();
    expect(session.revokeOtherSessions).toHaveBeenCalled();
  });
});
