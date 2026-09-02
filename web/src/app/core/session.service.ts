import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, finalize, map, of, shareReplay, switchMap, tap, throwError } from 'rxjs';

import { environment } from '../../environments/environment';
import { SessionState, TokenResponse, UserProfile } from './session.models';

@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly tokenState = signal<string | null>(null);
  private refreshRequest?: Observable<boolean>;

  readonly state = signal<SessionState>('anonymous');
  readonly profile = signal<UserProfile | null>(null);
  readonly isAuthenticated = computed(() => this.state() === 'authenticated');
  readonly isAdministrator = computed(() =>
    this.profile()?.permissions.some(
      (permission) => permission.key === 'access.admin' && permission.organizations === null
    ) ?? false
  );

  accessToken(): string | null {
    return this.tokenState();
  }

  hasPermission(key: string): boolean {
    return this.profile()?.permissions.some((permission) => permission.key === key) ?? false;
  }

  login(email: string, password: string): Observable<UserProfile> {
    this.state.set('loading');
    return this.http.post<TokenResponse>(
      `${environment.apiUrl}/auth/login`, { email, password }, { withCredentials: true }
    ).pipe(
      tap((token) => this.acceptToken(token)),
      switchMap(() => this.loadProfile()),
      catchError((error) => {
        this.clear('anonymous');
        return throwError(() => error);
      })
    );
  }

  refresh(): Observable<boolean> {
    if (this.refreshRequest) return this.refreshRequest;
    this.state.set('loading');
    this.refreshRequest = this.http.post<TokenResponse>(
      `${environment.apiUrl}/auth/refresh`, {}, { withCredentials: true }
    ).pipe(
      tap((token) => this.acceptToken(token)),
      switchMap(() => this.loadProfile()),
      map(() => true),
      catchError((error: HttpErrorResponse) => {
        this.clear(error.status === 0 || error.status >= 500 ? 'unavailable' : 'expired');
        return of(false);
      }),
      finalize(() => { this.refreshRequest = undefined; }),
      shareReplay(1)
    );
    return this.refreshRequest;
  }

  ensureSession(): Observable<boolean> {
    return this.accessToken() ? of(true) : this.refresh();
  }

  loadProfile(): Observable<UserProfile> {
    return this.http.get<UserProfile>(`${environment.apiUrl}/me`).pipe(
      tap((profile) => {
        this.profile.set(profile);
        this.state.set('authenticated');
      })
    );
  }

  updateProfile(payload: object): Observable<UserProfile> {
    return this.http.patch<UserProfile>(`${environment.apiUrl}/me`, payload).pipe(
      tap((profile) => this.profile.set(profile))
    );
  }

  uploadAvatar(file: File): Observable<UserProfile> {
    const body = new FormData();
    body.append('avatar', file);
    return this.http.post<UserProfile>(`${environment.apiUrl}/me/avatar`, body).pipe(
      tap((profile) => this.profile.set(profile))
    );
  }

  loadAvatar(): Observable<Blob> {
    return this.http.get(`${environment.apiUrl}/me/avatar`, { responseType: 'blob' });
  }

  removeAvatar(): Observable<UserProfile> {
    return this.http.delete<UserProfile>(`${environment.apiUrl}/me/avatar`).pipe(
      tap((profile) => this.profile.set(profile))
    );
  }

  logout(): Observable<void> {
    return this.http.post(
      `${environment.apiUrl}/auth/logout`, {}, { withCredentials: true }
    ).pipe(
      catchError(() => of(null)),
      tap(() => {
        this.clear('anonymous');
        void this.router.navigateByUrl('/login');
      }),
      map(() => undefined)
    );
  }

  clear(state: SessionState = 'expired'): void {
    this.tokenState.set(null);
    this.profile.set(null);
    this.state.set(state);
  }

  private acceptToken(token: TokenResponse): void {
    this.tokenState.set(token.access_token);
  }
}
