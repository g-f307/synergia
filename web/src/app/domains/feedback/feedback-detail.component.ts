import { Component, ElementRef, Injector, afterNextRender, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule, NgForm } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subject, catchError, combineLatest, map, of, startWith, switchMap, tap } from 'rxjs';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { StateComponent } from '../../shared/ui/ui-kit';
import { FeedbackItem, FeedbackService, FeedbackState } from './feedback.service';

@Component({ selector: 'syn-feedback-detail', imports: [FormsModule, RouterLink, StateComponent], templateUrl: './feedback-detail.component.html', styleUrl: './feedback.css' })
export class FeedbackDetailComponent {
  private readonly injector = inject(Injector);
  private readonly errorState = viewChild<ElementRef<HTMLElement>>('errorState');
  readonly i18n = inject(I18nService); readonly api = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute); readonly triage = this.route.snapshot.data['triage'] === true;
  readonly item = signal<FeedbackItem | null>(null); readonly loading = signal(true); readonly busy = signal(false); readonly failure = signal<ApiFailure | null>(null); readonly saved = signal(false);
  private readonly refresh = new Subject<void>();
  state: FeedbackState = 'under_review'; reason = '';
  constructor() {
    combineLatest([this.route.paramMap, this.refresh.pipe(startWith(undefined))]).pipe(
      tap(() => { this.loading.set(true); this.failure.set(null); }),
      switchMap(([params]) => this.api.detail(this.triage, params.get('feedbackId') ?? '').pipe(map((value) => ({ value, failure: null })), catchError((failure: ApiFailure) => of({ value: null, failure })))),
      takeUntilDestroyed()
    ).subscribe(({ value, failure }) => { this.item.set(value); this.state = value?.allowed_transitions[0] ?? 'under_review'; this.failure.set(failure); this.loading.set(false); });
  }
  retry(): void { this.refresh.next(); }
  terminal(): boolean { return this.state === 'resolved' || this.state === 'discarded'; }
  submit(form: NgForm): void {
    const item = this.item();
    if (!item || form.invalid || this.busy() || this.failure()?.status === 409) { form.control.markAllAsTouched(); return; }
    this.busy.set(true); this.failure.set(null); this.saved.set(false);
    this.api.transition(item, this.state, this.reason).subscribe({
      next: (value) => { this.item.set(value); this.reason = ''; this.state = value.allowed_transitions[0] ?? 'under_review'; this.saved.set(true); this.busy.set(false); form.resetForm({state: this.state, reason: ''}); },
      error: (failure: ApiFailure) => { this.failure.set(failure); this.busy.set(false); afterNextRender(() => this.errorState()?.nativeElement.focus(), {injector: this.injector}); }
    });
  }
}
