import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';

@Component({
  standalone: true,
  template: '<p id="untrusted-content">{{ untrustedContent }}</p>',
})
class UntrustedContentFixture {
  untrustedContent = '<img src=x onerror=alert(1)><script>alert(2)</script>';
}

describe('untrusted content rendering', () => {
  it('renders HTML and JavaScript payloads only as text', async () => {
    await TestBed.configureTestingModule({ imports: [UntrustedContentFixture] }).compileComponents();
    const fixture = TestBed.createComponent(UntrustedContentFixture);
    fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement.querySelector('#untrusted-content');

    expect(element.textContent).toBe(fixture.componentInstance.untrustedContent);
    expect(element.querySelector('img')).toBeNull();
    expect(element.querySelector('script')).toBeNull();
  });
});
