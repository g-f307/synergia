import { AfterViewInit, Component, ElementRef, HostListener, OnDestroy, inject, input, output } from '@angular/core';

import { I18nService } from '../i18n/i18n.service';

export type UiState = 'loading' | 'empty' | 'partial' | 'stale' | 'error' | 'forbidden' | 'unavailable' | 'success';

@Component({ selector: 'syn-card', template: '<section class="ui-card"><ng-content /></section>' })
export class CardComponent {}

@Component({ selector: 'syn-badge', template: '<span class="badge" [attr.data-tone]="tone()"><ng-content /></span>' })
export class BadgeComponent { readonly tone = input<UiState>('success'); }

@Component({ selector: 'syn-state', template: '<section class="state" [attr.data-state]="state()" role="status"><h2>{{ title() }}</h2><p>{{ message() }}</p><ng-content /></section>' })
export class StateComponent { readonly state = input.required<UiState>(); readonly title = input.required<string>(); readonly message = input.required<string>(); }

@Component({ selector: 'syn-alert', template: '<div class="state" data-state="error" role="alert"><strong>{{ title() }}</strong><p>{{ message() }}</p></div>' })
export class AlertComponent { readonly title = input.required<string>(); readonly message = input.required<string>(); }

@Component({ selector: 'syn-pagination', template: '<nav [attr.aria-label]="i18n.t(\'pagination.label\')"><button type="button" class="secondary" [disabled]="page() <= 1" (click)="pageChange.emit(page()-1)">{{ i18n.t(\'pagination.previous\') }}</button><span aria-live="polite">{{ i18n.t(\'pagination.status\', { page: i18n.formatNumber(page()), pages: i18n.formatNumber(pages()) }) }}</span><button type="button" class="secondary" [disabled]="page() >= pages()" (click)="pageChange.emit(page()+1)">{{ i18n.t(\'pagination.next\') }}</button></nav>', styles: ['nav{align-items:center;display:flex;gap:var(--space-3);justify-content:flex-end}'] })
export class PaginationComponent { readonly i18n = inject(I18nService); readonly page = input.required<number>(); readonly pages = input.required<number>(); readonly pageChange = output<number>(); }

@Component({ selector: 'syn-responsive-table', template: '<div class="table" tabindex="0" role="region" [attr.aria-label]="i18n.t(\'accessibility.horizontalTable\')"><ng-content /></div>', styles: ['.table{max-width:100%;overflow:auto}.table:focus{outline:.1875rem solid var(--color-focus)}'] })
export class ResponsiveTableComponent { readonly i18n = inject(I18nService); }

@Component({ selector: 'syn-modal', template: '<div class="backdrop"><section role="dialog" aria-modal="true" [attr.aria-label]="title()" tabindex="-1"><h2>{{ title() }}</h2><ng-content /><button type="button" class="secondary" (click)="close()">{{ i18n.t(\'common.close\') }}</button></section></div>', styles: ['.backdrop{background:rgb(0 0 0/60%);display:grid;inset:0;padding:var(--space-4);place-items:center;position:fixed;z-index:30}section{background:var(--color-surface);border-radius:var(--radius-md);max-width:36rem;padding:var(--space-5);width:100%}'] })
export class ModalComponent implements AfterViewInit, OnDestroy {
  private readonly host = inject(ElementRef<HTMLElement>);
  readonly i18n = inject(I18nService);
  private readonly previousFocus = document.activeElement as HTMLElement | null;
  readonly title = input.required<string>(); readonly dismissed = output<void>();
  ngAfterViewInit(): void { this.focus(); }
  ngOnDestroy(): void { this.previousFocus?.focus(); }
  @HostListener('document:keydown.escape') onEscape(): void { this.close(); }
  @HostListener('document:keydown', ['$event'])
  trapFocus(event: KeyboardEvent): void {
    if (event.key !== 'Tab') return;
    const dialog = (this.host.nativeElement as HTMLElement).querySelector<HTMLElement>('[role=dialog]');
    const controls = [...(this.host.nativeElement as HTMLElement).querySelectorAll<HTMLElement>('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')].filter((element) => !element.hasAttribute('disabled'));
    if (!controls.length) return;
    const first = controls[0];
    const last = controls[controls.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === dialog || !this.host.nativeElement.contains(active))) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && (active === last || !this.host.nativeElement.contains(active))) { event.preventDefault(); first.focus(); }
  }
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

@Component({ selector: 'syn-confirmation', imports: [ModalComponent, ButtonComponent], template: '<syn-modal [title]="title()" (dismissed)="cancelled.emit()"><p>{{ message() }}</p><div class="actions"><syn-button variant="secondary" (pressed)="cancelled.emit()">{{ i18n.t(\'common.cancel\') }}</syn-button><syn-button (pressed)="confirmed.emit()">{{ confirmLabel() || i18n.t(\'common.confirm\') }}</syn-button></div></syn-modal>', styles: ['.actions{display:flex;gap:var(--space-3);justify-content:flex-end}'] })
export class ConfirmationComponent { readonly i18n = inject(I18nService); readonly title = input.required<string>(); readonly message = input.required<string>(); readonly confirmLabel = input(''); readonly confirmed = output<void>(); readonly cancelled = output<void>(); }
