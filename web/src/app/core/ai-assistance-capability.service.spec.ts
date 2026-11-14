import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../environments/environment';
import { AiAssistanceCapabilityService } from './ai-assistance-capability.service';
import { SessionService } from './session.service';

describe('AiAssistanceCapabilityService', () => {
  let service: AiAssistanceCapabilityService;
  let http: HttpTestingController;
  let permissions: Set<string>;

  beforeEach(() => {
    permissions = new Set();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(), provideHttpClientTesting(),
        { provide: SessionService, useValue: { hasPermission: (key: string) => permissions.has(key) } }
      ]
    });
    service = TestBed.inject(AiAssistanceCapabilityService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('does not request metadata without execution and assistance permissions', () => {
    service.load().subscribe((result) => {
      expect(result).toEqual({ enabled: false, read: false, generate: false });
    });
    permissions.add('execution.read');
    service.load().subscribe((result) => expect(result.enabled).toBeFalse());
    http.expectNone(`${environment.apiUrl}/me/ai-assistance-capability`);
  });

  for (const action of ['read', 'generate']) {
    it(`requests only public capability for ${action} permission`, () => {
      permissions.add('execution.read');
      permissions.add(`ai.assistance.${action}`);
      const capability = { enabled: true, read: action === 'read', generate: action === 'generate' };
      service.load().subscribe((result) => expect(result).toEqual(capability));
      const request = http.expectOne(`${environment.apiUrl}/me/ai-assistance-capability`);
      expect(request.request.method).toBe('GET');
      expect(request.request.body).toBeNull();
      request.flush(capability);
    });
  }
});
