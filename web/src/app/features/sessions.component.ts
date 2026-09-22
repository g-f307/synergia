import { Component, OnInit, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';

import { ActiveSession } from '../core/session.models';
import { SessionService } from '../core/session.service';
import { I18nService } from '../shared/i18n/i18n.service';

@Component({
  selector: 'syn-sessions',
  template: `
    <section class="card sessions" aria-labelledby="sessions-title">
      <div class="sessions-heading">
        <h2 id="sessions-title">{{ i18n.t('sessions.title') }}</h2>
        <button type="button" class="secondary" (click)="load()" [disabled]="busy()">
          {{ i18n.t('sessions.refresh') }}
        </button>
      </div>
      <p>{{ i18n.t('sessions.description') }}</p>
      @if (error()) { <p class="error" role="alert">{{ i18n.t('sessions.error') }}</p> }
      @if (notice()) { <p class="success" role="status">{{ notice() }}</p> }
      @if (sessions().length) {
        <ul class="session-list">
          @for (item of sessions(); track item.id) {
            <li>
              <div>
                <strong>{{ item.device }}</strong>
                @if (item.current) { <span class="badge">{{ i18n.t('sessions.current') }}</span> }
                <dl>
                  <div><dt>{{ i18n.t('sessions.created') }}</dt><dd>{{ date(item.created_at) }}</dd></div>
                  <div><dt>{{ i18n.t('sessions.lastUsed') }}</dt><dd>{{ date(item.last_used_at) }}</dd></div>
                  <div><dt>{{ i18n.t('sessions.expires') }}</dt><dd>{{ date(item.expires_at) }}</dd></div>
                </dl>
              </div>
              <button type="button" class="secondary" [disabled]="busy()"
                [attr.aria-label]="item.current ? i18n.t('sessions.revokeCurrent') : i18n.t('sessions.revoke')"
                (click)="revoke(item)">
                {{ item.current ? i18n.t('sessions.revokeCurrent') : i18n.t('sessions.revoke') }}
              </button>
            </li>
          }
        </ul>
        <button type="button" class="secondary" [disabled]="busy() || sessions().length < 2"
          (click)="revokeOthers()">{{ i18n.t('sessions.revokeOthers') }}</button>
      } @else if (!busy() && !error()) {
        <p>{{ i18n.t('sessions.empty') }}</p>
      }
    </section>
  `,
  styles: [`
    .sessions{display:grid;gap:var(--syn-space-4)}.sessions h2{margin:0}.sessions-heading{align-items:center;display:flex;justify-content:space-between;gap:var(--syn-space-3)}
    .session-list{display:grid;gap:var(--syn-space-3);list-style:none;margin:0;padding:0}.session-list li{align-items:start;border:1px solid var(--syn-border);border-radius:var(--syn-radius);display:flex;gap:var(--syn-space-4);justify-content:space-between;padding:var(--syn-space-4)}
    dl{display:flex;flex-wrap:wrap;gap:var(--syn-space-3);margin:var(--syn-space-2) 0 0}dl div{display:grid}dt{color:var(--syn-text-secondary);font-size:.875rem}dd{margin:0}.badge{margin-left:var(--syn-space-2)}
    @media(max-width:767px){.session-list li{display:grid}.session-list button{width:100%}}
  `]
})
export class SessionsComponent implements OnInit {
  readonly i18n = inject(I18nService);
  private readonly session = inject(SessionService);
  readonly sessions = signal<ActiveSession[]>([]);
  readonly busy = signal(false);
  readonly error = signal(false);
  readonly notice = signal('');

  ngOnInit(): void { this.load(); }

  date(value: string): string {
    return this.i18n.formatDate(value, { timeStyle: 'short' });
  }

  load(): void {
    this.busy.set(true);
    this.error.set(false);
    this.session.listSessions().pipe(finalize(() => this.busy.set(false))).subscribe({
      next: (items) => this.sessions.set(items),
      error: () => this.error.set(true)
    });
  }

  revoke(item: ActiveSession): void {
    const key = item.current ? 'sessions.confirmCurrent' : 'sessions.confirmRevoke';
    if (!window.confirm(this.i18n.t(key))) return;
    this.busy.set(true);
    this.error.set(false);
    this.session.revokeSession(item).pipe(finalize(() => this.busy.set(false))).subscribe({
      next: () => {
        if (!item.current) {
          this.sessions.update((items) => items.filter((entry) => entry.id !== item.id));
          this.notice.set(this.i18n.t('sessions.revoked'));
        }
      },
      error: () => this.error.set(true)
    });
  }

  revokeOthers(): void {
    if (!window.confirm(this.i18n.t('sessions.confirmOthers'))) return;
    this.busy.set(true);
    this.error.set(false);
    this.session.revokeOtherSessions().pipe(finalize(() => this.busy.set(false))).subscribe({
      next: () => {
        this.sessions.update((items) => items.filter((item) => item.current));
        this.notice.set(this.i18n.t('sessions.othersRevoked'));
      },
      error: () => this.error.set(true)
    });
  }
}
