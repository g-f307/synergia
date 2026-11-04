import { Component, ElementRef, Injector, afterNextRender, inject, signal, viewChild } from '@angular/core';
import { FormsModule, NgForm } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { StateComponent } from '../../shared/ui/ui-kit';
import { FeedbackItem, FeedbackKind, FeedbackPolicy, FeedbackService } from './feedback.service';

@Component({ selector: 'syn-feedback-create', imports: [FormsModule, RouterLink, StateComponent], templateUrl: './feedback-create.component.html', styleUrl: './feedback.css' })
export class FeedbackCreateComponent {
  private readonly injector = inject(Injector);
  private readonly errorState = viewChild<ElementRef<HTMLElement>>('errorState');
  readonly i18n = inject(I18nService);
  readonly api = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  readonly policy = signal<FeedbackPolicy | null>(null);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly failure = signal<ApiFailure | null>(null);
  readonly created = signal<FeedbackItem | null>(null);
  kind: FeedbackKind = 'bug';
  title = ''; description = ''; expected = ''; observed = ''; source = '';
  constructor() { this.load(); }
  load(): void {
    this.loading.set(true); this.failure.set(null);
    this.api.policy().subscribe({
      next: (policy) => {
        this.policy.set(policy); this.loading.set(false);
        const source = this.route.snapshot.queryParamMap.get('source') ?? 'profile';
        this.source = policy.sources.some((item) => item.id === source) ? source : 'profile';
      },
      error: (failure: ApiFailure) => { this.failure.set(failure); this.loading.set(false); }
    });
  }
  submit(form: NgForm): void {
    if (form.invalid || this.busy() || !this.policy()?.can_create) { form.control.markAllAsTouched(); return; }
    this.busy.set(true); this.failure.set(null);
    this.api.create({
      kind: this.kind, title: this.title, description: this.description, source_id: this.source,
      ...(this.kind === 'bug' ? { expected_result: this.expected.trim() || undefined, observed_result: this.observed.trim() || undefined } : {})
    }).subscribe({
      next: (item) => { this.created.set(item); this.busy.set(false); },
      error: (failure: ApiFailure) => { this.failure.set(failure); this.busy.set(false); afterNextRender(() => this.errorState()?.nativeElement.focus(), {injector: this.injector}); }
    });
  }
}
