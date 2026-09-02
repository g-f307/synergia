import { TestBed } from '@angular/core/testing';

import { StateComponent } from './ui-kit';

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
