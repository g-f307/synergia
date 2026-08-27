import { AsyncPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, inject } from '@angular/core';
import { catchError, of } from 'rxjs';

interface HealthResponse {
  status: string;
  service: string;
}

@Component({
  selector: 'app-root',
  imports: [AsyncPipe],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  private readonly http = inject(HttpClient);

  readonly title = 'SYNERGIA';
  readonly health$ = this.http
    .get<HealthResponse>('http://localhost:8000/health')
    .pipe(catchError(() => of(null)));
}
