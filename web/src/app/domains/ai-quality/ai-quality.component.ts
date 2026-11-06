import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiFailure } from '../../shared/api/api-error';
import { I18nService } from '../../shared/i18n/i18n.service';
import { TranslationKey } from '../../shared/i18n/i18n.models';
import { BadgeComponent, ResponsiveTableComponent, StateComponent } from '../../shared/ui/ui-kit';
import { AiQualityService, FactValue, QualityExplanation, QualityModelStatus, QualityResponse, QualityScenario, scenarioNames } from './ai-quality.service';

@Component({
  selector: 'syn-ai-quality', imports: [FormsModule, BadgeComponent, ResponsiveTableComponent, StateComponent],
  templateUrl: './ai-quality.component.html', styleUrl: './ai-quality.component.css'
})
export class AiQualityComponent {
  readonly i18n = inject(I18nService);
  private readonly api = inject(AiQualityService);
  private readonly destroy = inject(DestroyRef);
  readonly scenarios = signal<QualityScenario[]>([]);
  readonly selectedId = signal('');
  readonly selected = computed(() => this.scenarios().find(s => s.id === this.selectedId()));
  readonly loading = signal(true);
  readonly modelStatus = signal<QualityModelStatus>('disabled');
  readonly generating = signal(false);
  readonly failure = signal<ApiFailure | null>(null);
  readonly response = signal<QualityResponse | null>(null);
  readonly names = scenarioNames;

  constructor() { this.load(); }

  load(): void {
    if (this.generating()) return;
    this.loading.set(true); this.failure.set(null);
    this.response.set(null);
    this.api.catalog().pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: value => {
        this.modelStatus.set(value.model_status);
        this.scenarios.set(value.scenarios);
        this.selectedId.set(value.scenarios.find(s => s.id === 'QE-A02')?.id ?? value.scenarios[0]?.id ?? '');
        this.loading.set(false);
      },
      error: (error: ApiFailure) => { this.failure.set(error); this.loading.set(false); }
    });
  }

  select(id: string): void {
    if (this.generating()) return;
    this.selectedId.set(id); this.response.set(null); this.failure.set(null);
  }

  generate(): void {
    const scenario = this.selected();
    if (!scenario || this.generating() || !scenario.groups.length || this.modelStatus() !== 'available') return;
    this.generating.set(true); this.failure.set(null); this.response.set(null);
    this.api.generate(scenario.id).pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: response => { this.response.set(response); this.generating.set(false); },
      error: (error: ApiFailure) => { this.failure.set(error); this.generating.set(false); }
    });
  }

  explanation(code: string): QualityExplanation | undefined { return this.response()?.groups.find(g => g.group.code === code); }
  fact(value: FactValue): string { return value.state === 'known' ? String(value.value) : this.i18n.t('quality.notProvided'); }
  rejection(code: string): string {
    const keys: Record<string, TranslationKey> = {
      runtime_timeout: 'quality.timeout', runtime_busy: 'quality.busy', runtime_unavailable: 'quality.unavailable',
      invalid_json: 'quality.rejected', invalid_output_schema: 'quality.rejected', unsupported_explanation: 'quality.rejected',
      unsupported_human_check: 'quality.rejected', duplicate_json_key: 'quality.rejected', output_too_large: 'quality.rejected'
    };
    return this.i18n.t(keys[code] ?? 'quality.rejected');
  }
}
