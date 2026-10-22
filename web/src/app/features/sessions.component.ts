import { Component, OnInit, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';

import { ActiveSession } from '../core/session.models';
import { SessionService } from '../core/session.service';
import { I18nService } from '../shared/i18n/i18n.service';
import { ConfirmationComponent } from '../shared/ui/ui-kit';

@Component({
  selector: 'syn-sessions',
  imports: [ConfirmationComponent],
  template: `
    <section class="sessions" aria-labelledby="sessions-title">
      <div class="sessions-heading">
        <h2 id="sessions-title">{{ i18n.t('sessions.title') }}</h2>
        <button type="button" class="secondary" (click)="load()" [disabled]="busy()">
          {{ i18n.t('sessions.refresh') }}
        </button>
      </div>
      <p class="sessions-description">{{ i18n.t('sessions.description') }}</p>
      @if (error()) { <p class="error" role="alert">{{ i18n.t('sessions.error') }}</p> }
      @if (notice()) { <p class="success" role="status">{{ notice() }}</p> }
      @if (sessions().length) {
        <ul class="session-list">
          @for (item of sessions(); track item.id) {
            <li class="session-row">
              <div class="device-identity">
                <div class="device-icons" aria-hidden="true">
                  @for (icon of deviceIcons(item.device); track icon) {
                    <span class="device-icon-shell"><img class="device-icon" [src]="icon" alt="" width="28" height="28"></span>
                  }
                </div>
                <div class="session-copy"><div class="device-title">
                <strong>{{ item.device }}</strong>
                @if (item.current) { <span class="badge">{{ i18n.t('sessions.current') }}</span> }
                </div><dl>
                  <div><dt>{{ i18n.t('sessions.created') }}</dt><dd>{{ date(item.created_at) }}</dd></div>
                  <div><dt>{{ i18n.t('sessions.lastUsed') }}</dt><dd>{{ date(item.last_used_at) }}</dd></div>
                  <div><dt>{{ i18n.t('sessions.expires') }}</dt><dd>{{ date(item.expires_at) }}</dd></div>
                </dl></div>
              </div>
              <button type="button" class="secondary" [disabled]="busy()"
                [attr.aria-label]="item.current ? i18n.t('sessions.revokeCurrent') : i18n.t('sessions.revoke')"
                (click)="revoke(item)">
                {{ item.current ? i18n.t('sessions.revokeCurrent') : i18n.t('sessions.revoke') }}
              </button>
            </li>
          }
        </ul>
        <button type="button" class="secondary revoke-others" [disabled]="busy() || sessions().length < 2"
          (click)="revokeOthers()">{{ i18n.t('sessions.revokeOthers') }}</button>
      } @else if (!busy() && !error()) {
        <p>{{ i18n.t('sessions.empty') }}</p>
      }
    </section>
    @if (pendingRevocation(); as pending) {
      <syn-confirmation
        [title]="i18n.t('common.confirm')"
        [message]="pending === 'others' ? i18n.t('sessions.confirmOthers') : i18n.t(pending.current ? 'sessions.confirmCurrent' : 'sessions.confirmRevoke')"
        (confirmed)="confirmRevocation()"
        (cancelled)="cancelRevocation()"
      />
    }
  `,
  styles: [`
    .sessions{--line:color-mix(in srgb,var(--syn-text) 9%,transparent);background:var(--syn-bg);border:1px solid var(--line);border-radius:20px;display:grid;gap:18px;padding:clamp(22px,3vw,34px)}.sessions h2,.sessions-description{margin:0}.sessions-description{color:var(--syn-text-secondary);font-size:.88rem;margin-top:-10px}.sessions-heading{align-items:center;display:flex;gap:16px;justify-content:space-between}.sessions-heading button,.revoke-others{border-radius:999px}.session-list{border:1px solid var(--line);border-radius:18px;display:grid;list-style:none;margin:0;overflow:hidden;padding:0}.session-row{align-items:center;background:var(--syn-bg-card);border-bottom:1px solid var(--line);display:flex;gap:20px;justify-content:space-between;min-height:104px;padding:18px 20px}.session-row:last-child{border-bottom:0}.device-identity{align-items:center;display:flex;gap:18px;min-width:0}.device-marks{display:flex;min-width:82px}.device-mark{align-items:center;background:var(--syn-primary);border:3px solid var(--syn-bg-card);border-radius:50%;color:#fff;display:flex;font-size:.66rem;font-weight:800;height:46px;justify-content:center;letter-spacing:-.02em;width:46px}.device-mark-os{background:color-mix(in srgb,var(--syn-primary) 58%,var(--syn-text));margin-left:-10px}.session-copy{min-width:0}.device-title{align-items:center;display:flex;flex-wrap:wrap;gap:8px}.device-title strong{overflow-wrap:anywhere}.badge{background:color-mix(in srgb,var(--syn-primary) 10%,var(--syn-bg-card));border:1px solid color-mix(in srgb,var(--syn-primary) 22%,transparent);border-radius:999px;color:var(--syn-primary);font-size:.72rem;padding:4px 8px}dl{display:flex;flex-wrap:wrap;gap:12px 22px;margin:10px 0 0}dl div{display:grid;gap:2px}dt{color:var(--syn-text-secondary);font-size:.72rem}dd{font-size:.82rem;font-variant-numeric:tabular-nums;margin:0}.session-row>button{border-radius:999px;flex:0 0 auto}.revoke-others{justify-self:end}
    .sessions{background:transparent;border:0;border-radius:0;border-top:1px solid var(--line);padding:28px 0 0}.session-list{border:0;border-radius:0;overflow:visible}.session-row{background:transparent;padding-left:4px;padding-right:4px}.session-row:first-child{border-top:1px solid var(--line)}.device-icons{display:flex;min-width:82px}.device-icon-shell{align-items:center;background:#fff;border:1px solid #dfe2e7;border-radius:50%;box-shadow:0 3px 10px rgb(22 27 34 / 8%);display:flex;height:46px;justify-content:center;width:46px}.device-icon-shell+.device-icon-shell{margin-left:-10px}.device-icon{display:block;height:28px;object-fit:contain;width:28px}
    @media(max-width:767px){.session-row{align-items:stretch;display:grid}.session-row>button{width:100%}.device-icons{min-width:72px}.device-icon-shell{height:40px;width:40px}.device-icon{height:24px;width:24px}.revoke-others{justify-self:stretch;width:100%}}
  `]
})
export class SessionsComponent implements OnInit {
  readonly i18n = inject(I18nService);
  private readonly session = inject(SessionService);
  readonly sessions = signal<ActiveSession[]>([]);
  readonly busy = signal(false);
  readonly error = signal(false);
  readonly notice = signal('');
  readonly pendingRevocation = signal<ActiveSession | 'others' | null>(null);

  ngOnInit(): void { this.load(); }

  date(value: string): string {
    return this.i18n.formatDate(value, { timeStyle: 'short' });
  }

  deviceIcons(device: string): [string, string] {
    const [browser = '', system = ''] = device.split('/').map((part) => part.trim().toLowerCase());
    return [this.browserIcon(browser), this.systemIcon(system)];
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
    this.pendingRevocation.set(item);
  }

  revokeOthers(): void {
    this.pendingRevocation.set('others');
  }

  cancelRevocation(): void {
    this.pendingRevocation.set(null);
  }

  confirmRevocation(): void {
    const pending = this.pendingRevocation();
    this.pendingRevocation.set(null);
    if (!pending) return;
    if (pending === 'others') {
      this.revokeOtherSessions();
      return;
    }
    this.revokeSession(pending);
  }

  private revokeSession(item: ActiveSession): void {
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

  private revokeOtherSessions(): void {
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

  private browserIcon(browser: string): string {
    if (browser.includes('chrome')) return '/assets/icons/device-chrome.svg';
    if (browser.includes('firefox')) return '/assets/icons/device-firefox.svg';
    if (browser.includes('edge')) return '/assets/icons/device-edge.svg';
    if (browser.includes('safari')) return '/assets/icons/device-safari.svg';
    return '/assets/icons/device-browser.svg';
  }

  private systemIcon(system: string): string {
    if (system.includes('windows')) return '/assets/icons/device-windows.svg';
    if (system.includes('macos')) return '/assets/icons/device-apple.svg';
    if (system.includes('linux')) return '/assets/icons/device-linux.svg';
    if (system.includes('android')) return '/assets/icons/device-android.svg';
    if (system.includes('ios')) return '/assets/icons/device-apple.svg';
    return '/assets/icons/device-system.svg';
  }
}
