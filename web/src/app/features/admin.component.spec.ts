import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { I18nService } from '../shared/i18n/i18n.service';
import { AdminComponent } from './admin.component';

describe('AdminComponent', () => {
  it('represents forbidden access separately from service unavailability', () => {
    const http = {
      get: () => throwError(() => new HttpErrorResponse({ status: 403 }))
    };
    TestBed.configureTestingModule({
      imports: [AdminComponent],
      providers: [{ provide: HttpClient, useValue: http }]
    });

    const fixture = TestBed.createComponent(AdminComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Acesso negado');
    expect(fixture.nativeElement.textContent).not.toContain('Administração indisponível');
  });

  it('translates known user statuses and safely hides unknown codes', () => {
    const http = {
      get: (url: string) => of(url.endsWith('/users') ? {
        items: [
          { id: 'user-1', display_name: 'First user', status: 'active' },
          { id: 'user-2', display_name: 'Second user', status: 'future_code' }
        ],
        total: 2
      } : { items: [], total: 0 })
    };
    TestBed.configureTestingModule({
      imports: [AdminComponent],
      providers: [{ provide: HttpClient, useValue: http }]
    });
    TestBed.inject(I18nService).configure('en-US');

    const fixture = TestBed.createComponent(AdminComponent);
    fixture.detectChanges();
    const content = fixture.nativeElement.textContent;

    expect(content).toContain('First user — Active');
    expect(content).toContain('Second user — Unknown status');
    expect(content).not.toContain('future_code');
  });
});
