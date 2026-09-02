import { TestBed } from '@angular/core/testing';

import { ButtonComponent, ConfirmationComponent, FieldComponent, StateComponent } from './ui-kit';

describe('StateComponent', () => {
  it('exposes semantic state without relying on color alone', async () => {
    await TestBed.configureTestingModule({ imports: [StateComponent] }).compileComponents();
    const fixture = TestBed.createComponent(StateComponent);
    fixture.componentRef.setInput('state', 'forbidden');
    fixture.componentRef.setInput('title', 'Acesso proibido');
    fixture.componentRef.setInput('message', 'Permissão insuficiente.');
    fixture.detectChanges();
    const state = fixture.nativeElement.querySelector('[role=status]') as HTMLElement;
    expect(state.dataset['state']).toBe('forbidden');
    expect(state.textContent).toContain('Acesso proibido');
  });
});

describe('shared controls', () => {
  it('disables the button while loading', async () => {
    await TestBed.configureTestingModule({ imports: [ButtonComponent] }).compileComponents();
    const fixture = TestBed.createComponent(ButtonComponent);
    fixture.componentRef.setInput('loading', true);
    fixture.detectChanges();
    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(button.disabled).toBeTrue();
    expect(button.getAttribute('aria-busy')).toBe('true');
  });

  it('connects field errors to the input', async () => {
    await TestBed.configureTestingModule({ imports: [FieldComponent] }).compileComponents();
    const fixture = TestBed.createComponent(FieldComponent);
    fixture.componentRef.setInput('controlId', 'query');
    fixture.componentRef.setInput('label', 'Consulta');
    fixture.componentRef.setInput('error', 'Campo obrigatório');
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(input.getAttribute('aria-describedby')).toBe('query-error');
  });

  it('emits an explicit confirmation', async () => {
    await TestBed.configureTestingModule({ imports: [ConfirmationComponent] }).compileComponents();
    const fixture = TestBed.createComponent(ConfirmationComponent);
    fixture.componentRef.setInput('title', 'Confirmar ação');
    fixture.componentRef.setInput('message', 'A operação será registrada.');
    let confirmed = false;
    fixture.componentInstance.confirmed.subscribe(() => { confirmed = true; });
    fixture.detectChanges();
    const buttons = fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>;
    buttons[1].click();
    expect(confirmed).toBeTrue();
  });
});
