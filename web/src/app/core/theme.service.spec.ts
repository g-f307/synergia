import { TestBed } from '@angular/core/testing';

import { ThemeService } from './theme.service';

describe('ThemeService', () => {
  beforeEach(() => {
    document.documentElement.dataset['theme'] = 'light';
    TestBed.configureTestingModule({});
  });

  it('selects the official light and dark brand variants without a reload', () => {
    const service = TestBed.inject(ThemeService);

    expect(service.brandLogo()).toBe('/assets/logos/logo-horizontal.png');
    expect(service.brandLogo(true)).toBe('/assets/logos/simbolo.png');

    service.toggle();

    expect(document.documentElement.dataset['theme']).toBe('dark');
    expect(service.brandLogo()).toBe('/assets/logos/logo-negativa-horizontal.png');
    expect(service.brandLogo(true)).toBe('/assets/logos/simbolo-negativo.png');
  });
});
