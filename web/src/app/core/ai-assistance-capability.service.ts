import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, of } from 'rxjs';

import { environment } from '../../environments/environment';
import { SessionService } from './session.service';

export interface AiAssistanceCapability {
  enabled: boolean;
  read: boolean;
  generate: boolean;
}

/** Capability discovery only. The execution card is delivered in issue #190. */
@Injectable({ providedIn: 'root' })
export class AiAssistanceCapabilityService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);

  load(): Observable<AiAssistanceCapability> {
    if (!this.session.hasPermission('execution.read') || (
      !this.session.hasPermission('ai.assistance.read')
      && !this.session.hasPermission('ai.assistance.generate')
    )) {
      return of({ enabled: false, read: false, generate: false });
    }
    return this.http.get<AiAssistanceCapability>(
      `${environment.apiUrl}/me/ai-assistance-capability`
    );
  }
}
