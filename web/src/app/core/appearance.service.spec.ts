import { TestBed } from '@angular/core/testing';

import { AppearanceService } from './appearance.service';

describe('AppearanceService', () => {
  let service: AppearanceService;

  beforeEach(() => {
    service = TestBed.inject(AppearanceService);
    service.configure();
  });

  it('applies supported preferences to the document shell', () => {
    service.configure({ density: 'compact', font_scale: 'large' });

    expect(document.documentElement.dataset['density']).toBe('compact');
    expect(document.documentElement.dataset['fontScale']).toBe('large');
  });

  it('uses safe defaults for unknown values returned by an older contract', () => {
    service.configure({ density: 'unknown', font_scale: 'huge' } as never);

    expect(service.preferences()).toEqual({ density: 'comfortable', font_scale: 'normal' });
    expect(document.documentElement.dataset['density']).toBe('comfortable');
    expect(document.documentElement.dataset['fontScale']).toBe('normal');
  });
});
