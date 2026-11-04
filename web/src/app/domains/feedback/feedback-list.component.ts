import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subject, catchError, combineLatest, map, of, startWith, switchMap, tap } from 'rxjs';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { PaginationComponent, StateComponent } from '../../shared/ui/ui-kit';
import { FeedbackPage, FeedbackService, feedbackStates } from './feedback.service';

@Component({ selector: 'syn-feedback-list', imports: [FormsModule, RouterLink, PaginationComponent, StateComponent], templateUrl: './feedback-list.component.html', styleUrl: './feedback.css' })
export class FeedbackListComponent {
  readonly i18n = inject(I18nService); readonly api = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute); private readonly router = inject(Router);
  readonly triage = this.route.snapshot.data['triage'] === true;
  readonly states = feedbackStates;
  readonly result = signal<FeedbackPage | null>(null); readonly loading = signal(true); readonly failure = signal<ApiFailure | null>(null);
  private readonly refresh = new Subject<void>();
  protocol = ''; kind = ''; state = ''; from = ''; to = '';
  constructor() {
    combineLatest([this.route.queryParamMap, this.refresh.pipe(startWith(undefined))]).pipe(
      tap(([params]) => { this.protocol = params.get('protocol') ?? ''; this.kind = params.get('kind') ?? ''; this.state = params.get('state') ?? ''; this.from = params.get('from') ?? ''; this.to = params.get('to') ?? ''; this.loading.set(true); this.failure.set(null); }),
      switchMap(([params]) => {
        const page = Math.min(10000, Math.max(1, Number(params.get('page')) || 1));
        const filters: Record<string, string> = { protocol: this.protocol, kind: this.kind, state: this.state };
        if (/^\d{4}-\d{2}-\d{2}$/.test(this.from)) filters['created_from'] = this.from + 'T00:00:00Z';
        if (/^\d{4}-\d{2}-\d{2}$/.test(this.to)) filters['created_to'] = this.to + 'T00:00:00Z';
        return this.api.list(this.triage, page, filters).pipe(map((value) => ({ value, failure: null })), catchError((failure: ApiFailure) => of({ value: null, failure })));
      }), takeUntilDestroyed()
    ).subscribe(({ value, failure }) => { this.result.set(value); this.failure.set(failure); this.loading.set(false); });
  }
  apply(): void { this.navigate(1); }
  navigate(page: number): void { void this.router.navigate([], { relativeTo: this.route, queryParams: { protocol: this.protocol || null, kind: this.kind || null, state: this.state || null, from: this.from || null, to: this.to || null, page } }); }
  retry(): void { this.refresh.next(); }
}
