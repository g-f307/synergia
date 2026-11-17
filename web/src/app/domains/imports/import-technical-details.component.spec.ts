import { TestBed } from '@angular/core/testing';

import { ImportTechnicalDetailsComponent } from './import-technical-details.component';

describe('Import technical details', () => {
  let original: PropertyDescriptor | undefined;
  let write: jasmine.Spy;
  beforeEach(() => {
    original = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
    write = jasmine.createSpy('writeText').and.resolveTo(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: write } });
    TestBed.configureTestingModule({ imports: [ImportTechnicalDetailsComponent] });
  });
  afterEach(() => {
    if (original) Object.defineProperty(navigator, 'clipboard', original);
    else Reflect.deleteProperty(navigator, 'clipboard');
  });
  function create() {
    const fixture = TestBed.createComponent(ImportTechnicalDetailsComponent);
    fixture.componentRef.setInput('correlationId', 'corr-synthetic');
    fixture.componentRef.setInput('code', 'summary_unavailable'); fixture.detectChanges();
    return fixture;
  }
  it('starts collapsed and copies only the correlation ID', async () => {
    const fixture = create();
    expect(fixture.nativeElement.querySelector('details').open).toBeFalse();
    await fixture.componentInstance.copy(fixture.nativeElement.querySelector('input')); fixture.detectChanges();
    expect(write).toHaveBeenCalledOnceWith('corr-synthetic');
    expect(fixture.nativeElement.textContent).toContain('ID de correlação copiado');
    fixture.componentRef.setInput('correlationId', 'corr-new'); fixture.detectChanges();
    expect(fixture.componentInstance.copyResult()).toBeNull();
  });
  it('keeps a selectable ID and announces manual copying if clipboard access fails', async () => {
    write.and.rejectWith(new Error('Synthetic denial'));
    const fixture = create(); fixture.nativeElement.querySelector('details').open = true;
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    await fixture.componentInstance.copy(input); fixture.detectChanges();
    expect(input.readOnly).toBeTrue(); expect(input.selectionStart).toBe(0);
    expect(input.selectionEnd).toBe(input.value.length);
    expect(fixture.nativeElement.textContent).toContain('função de copiar do dispositivo');
  });
});
