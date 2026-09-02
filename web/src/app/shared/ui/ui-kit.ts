import { Component, ElementRef, HostListener, inject, input, output } from '@angular/core';

export type UiState = 'loading' | 'empty' | 'partial' | 'stale' | 'error' | 'forbidden' | 'unavailable' | 'success';

@Component({ selector: 'syn-card', template: '<section class="ui-card"><ng-content /></section>', styles: ['.ui-card{background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-md);padding:var(--space-5)}'] })
export class CardComponent {}

@Component({ selector: 'syn-badge', template: '<span class="badge" [attr.data-tone]="tone()"><ng-content /></span>', styles: ['.badge{border:1px solid currentColor;border-radius:99rem;display:inline-flex;font-size:.875rem;font-weight:600;padding:var(--space-1) var(--space-2)}'] })
export class BadgeComponent { readonly tone = input<UiState>('success'); }

@Component({ selector: 'syn-state', template: '<section class="state" [attr.data-state]="state()" role="status"><h2>{{ title() }}</h2><p>{{ message() }}</p><ng-content /></section>', styles: ['.state{border-left:.25rem solid currentColor;padding:var(--space-4)}.state[data-state=error]{color:var(--color-error)}.state[data-state=partial]{color:var(--color-partial)}.state[data-state=unavailable]{color:var(--color-unavailable)}.state[data-state=success]{color:var(--color-success)}'] })
export class StateComponent { readonly state = input.required<UiState>(); readonly title = input.required<string>(); readonly message = input.required<string>(); }

@Component({ selector: 'syn-alert', template: '<div class="alert" role="alert"><strong>{{ title() }}</strong><p>{{ message() }}</p></div>', styles: ['.alert{border:1px solid currentColor;border-radius:var(--radius-sm);padding:var(--space-4)}'] })
export class AlertComponent { readonly title = input.required<string>(); readonly message = input.required<string>(); }

@Component({ selector: 'syn-pagination', template: '<nav aria-label="Paginação"><button type="button" class="secondary" [disabled]="page() <= 1" (click)="pageChange.emit(page()-1)">Anterior</button><span aria-live="polite">Página {{ page() }} de {{ pages() }}</span><button type="button" class="secondary" [disabled]="page() >= pages()" (click)="pageChange.emit(page()+1)">Próxima</button></nav>', styles: ['nav{align-items:center;display:flex;gap:var(--space-3);justify-content:flex-end}'] })
export class PaginationComponent { readonly page = input.required<number>(); readonly pages = input.required<number>(); readonly pageChange = output<number>(); }

@Component({ selector: 'syn-responsive-table', template: '<div class="table" tabindex="0" role="region" aria-label="Tabela com rolagem horizontal"><ng-content /></div>', styles: ['.table{max-width:100%;overflow:auto}.table:focus{outline:.1875rem solid var(--color-focus)}'] })
export class ResponsiveTableComponent {}

@Component({ selector: 'syn-modal', template: '<div class="backdrop"><section role="dialog" aria-modal="true" [attr.aria-label]="title()" tabindex="-1"><h2>{{ title() }}</h2><ng-content /><button type="button" class="secondary" (click)="close()">Fechar</button></section></div>', styles: ['.backdrop{background:rgb(0 0 0/60%);display:grid;inset:0;padding:var(--space-4);place-items:center;position:fixed;z-index:30}section{background:var(--color-surface);border-radius:var(--radius-md);max-width:36rem;padding:var(--space-5);width:100%}'] })
export class ModalComponent {
  private readonly host = inject(ElementRef<HTMLElement>);
  readonly title = input.required<string>(); readonly dismissed = output<void>();
  @HostListener('document:keydown.escape') onEscape(): void { this.close(); }
  close(): void { this.dismissed.emit(); }
  focus(): void { (this.host.nativeElement.querySelector('[role=dialog]') as HTMLElement | null)?.focus(); }
}
