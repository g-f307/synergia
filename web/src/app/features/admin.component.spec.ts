import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { I18nService } from '../shared/i18n/i18n.service';
import { AdminComponent } from './admin.component';

describe('AdminComponent', () => {
  it('presents the administrative overview as one navigable governance surface', () => {
    const http = {
      get: (url: string) => of(url.endsWith('/permissions') ? [
        { id: 'permission-1', permission_key: 'users.read' },
        { id: 'permission-2', permission_key: 'users.write' }
      ] : url.endsWith('/users') ? {
        items: [{ id: 'user-1', display_name: 'First user', status: 'active' }],
        total: 12
      } : url.endsWith('/groups') ? {
        items: [],
        total: 4
      } : {
        items: [],
        total: 3
      })
    };
    TestBed.configureTestingModule({
      imports: [AdminComponent],
      providers: [provideRouter([]), { provide: HttpClient, useValue: http }]
    });

    const fixture = TestBed.createComponent(AdminComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    const links = Array.from(root.querySelectorAll<HTMLAnchorElement>('.management-link'));

    expect(root.querySelector('.admin-page')).not.toBeNull();
    expect(root.querySelector('h1')?.textContent).toContain('Acesso e governança');
    expect(Array.from(root.querySelectorAll('.metric-value')).map((item) => item.textContent?.trim()))
      .toEqual(['12', '4', '3', '2']);
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/admin/users',
      '/admin/groups',
      '/admin/roles',
      '/admin/notification-templates'
    ]);
    expect(links[1].querySelector('img')?.getAttribute('src')).toBe('assets/icons/team.svg');
    expect(links[2].querySelector('img')?.getAttribute('src')).toBe('assets/icons/role-badge.svg');
    expect(root.querySelector('[data-testid="visual-catalog"]')).toBeNull();
    expect(getComputedStyle(root.querySelector('.admin-page') as HTMLElement).overflowY).toBe('auto');
  });

  it('represents forbidden access separately from service unavailability', () => {
    const http = {
      get: () => throwError(() => new HttpErrorResponse({ status: 403 }))
    };
    TestBed.configureTestingModule({
      imports: [AdminComponent],
      providers: [provideRouter([]), { provide: HttpClient, useValue: http }]
    });

    const fixture = TestBed.createComponent(AdminComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Acesso negado');
    expect(fixture.nativeElement.textContent).not.toContain('Administração indisponível');
  });

  it('translates known user statuses and safely hides unknown codes', () => {
    const http = {
      get: (url: string) => of(url.endsWith('/permissions') ? [] : url.endsWith('/users') ? {
        items: [
          { id: 'user-1', display_name: 'First user', status: 'active' },
          { id: 'user-2', display_name: 'Second user', status: 'future_code' }
        ],
        total: 2
      } : { items: [], total: 0 })
    };
    TestBed.configureTestingModule({
      imports: [AdminComponent],
      providers: [provideRouter([]), { provide: HttpClient, useValue: http }]
    });
    TestBed.inject(I18nService).configure('en-US');

    const fixture = TestBed.createComponent(AdminComponent);
    fixture.detectChanges();
    const content = fixture.nativeElement.textContent;

    expect(content).toContain('First user');
    expect(content).toContain('Active');
    expect(content).toContain('Second user');
    expect(content).toContain('Unknown status');
    expect(content).not.toContain('future_code');
    expect(fixture.nativeElement.querySelector('a[href="/admin/users/user-1"]')).not.toBeNull();
  });
});
