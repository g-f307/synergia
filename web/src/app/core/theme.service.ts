import { Injectable, signal } from '@angular/core';

export type Theme = 'light' | 'dark';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly active = signal<Theme>(
    document.documentElement.dataset['theme'] === 'dark' ? 'dark' : 'light'
  );

  constructor() {
    this.apply(this.active());
  }

  toggle(): void {
    this.apply(this.active() === 'dark' ? 'light' : 'dark');
  }

  brandLogo(compact = false): string {
    if (this.active() === 'dark') {
      return '/assets/logos/logo-dark-horizontal.svg';
    }
    if (compact) {
      return '/assets/logos/simbolo.png';
    }
    return '/assets/logos/logo-horizontal.png';
  }

  verticalBrandLogo(): string {
    return '/assets/logos/synergia-logo-vertical.svg';
  }

  private apply(theme: Theme): void {
    this.active.set(theme);
    document.documentElement.dataset['theme'] = theme;
  }
}
