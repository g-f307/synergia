import { AsyncPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, inject } from '@angular/core';
import { catchError, map, of, startWith } from 'rxjs';

import { environment } from '../environments/environment';

interface HealthResponse {
  status: string;
  service: string;
}

type HealthState =
  | { state: 'loading' }
  | { state: 'available'; service: string }
  | { state: 'unavailable' };

@Component({
  selector: 'app-root',
  imports: [AsyncPipe],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  private readonly http = inject(HttpClient);

  readonly title = 'SYNERGIA';
  readonly healthState$ = this.http
    .get<HealthResponse>(`${environment.apiUrl}/health`)
    .pipe(
      map((health): HealthState => ({ state: 'available', service: health.service })),
      startWith<HealthState>({ state: 'loading' }),
      catchError(() => of<HealthState>({ state: 'unavailable' }))
    );
}
