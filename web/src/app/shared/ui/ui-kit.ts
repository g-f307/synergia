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

@Component({ selector: 'syn-button', template: '<button type="button" [class.secondary]="variant() === \'secondary\'" [disabled]="disabled() || loading()" [attr.aria-busy]="loading()" (click)="pressed.emit()"><ng-content /></button>' })
export class ButtonComponent { readonly variant = input<'primary' | 'secondary'>('primary'); readonly disabled = input(false); readonly loading = input(false); readonly pressed = output<void>(); }

@Component({ selector: 'syn-field', template: '<label [attr.for]="controlId()">{{ label() }}<input [id]="controlId()" [type]="type()" [value]="value()" [disabled]="disabled()" [attr.aria-invalid]="error() ? true : null" [attr.aria-describedby]="error() ? controlId()+\'-error\' : null" (input)="valueChange.emit($any($event.target).value)"></label>@if (error()) {<span class="error" [id]="controlId()+\'-error\'">{{ error() }}</span>}' })
export class FieldComponent { readonly controlId = input.required<string>(); readonly label = input.required<string>(); readonly type = input<'text' | 'search' | 'email' | 'password'>('text'); readonly value = input(''); readonly disabled = input(false); readonly error = input(''); readonly valueChange = output<string>(); }

export interface SelectOption { value: string; label: string; }
@Component({ selector: 'syn-select', template: '<label [attr.for]="controlId()">{{ label() }}<select [id]="controlId()" [disabled]="disabled()" [value]="value()" (change)="valueChange.emit($any($event.target).value)">@for (option of options(); track option.value) {<option [value]="option.value">{{ option.label }}</option>}</select></label>' })
export class SelectComponent { readonly controlId = input.required<string>(); readonly label = input.required<string>(); readonly options = input.required<SelectOption[]>(); readonly value = input(''); readonly disabled = input(false); readonly valueChange = output<string>(); }

@Component({ selector: 'syn-confirmation', imports: [ModalComponent, ButtonComponent], template: '<syn-modal [title]="title()" (dismissed)="cancelled.emit()"><p>{{ message() }}</p><div class="actions"><syn-button variant="secondary" (pressed)="cancelled.emit()">Cancelar</syn-button><syn-button (pressed)="confirmed.emit()">{{ confirmLabel() }}</syn-button></div></syn-modal>', styles: ['.actions{display:flex;gap:var(--space-3);justify-content:flex-end}'] })
export class ConfirmationComponent { readonly title = input.required<string>(); readonly message = input.required<string>(); readonly confirmLabel = input('Confirmar'); readonly confirmed = output<void>(); readonly cancelled = output<void>(); }
