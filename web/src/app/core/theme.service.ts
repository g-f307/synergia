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
    if (compact) {
      return this.active() === 'dark'
        ? '/assets/logos/simbolo-negativo.png'
        : '/assets/logos/simbolo.png';
    }
    return this.active() === 'dark'
      ? '/assets/logos/logo-negativa-horizontal.png'
      : '/assets/logos/logo-horizontal.png';
  }

  private apply(theme: Theme): void {
    this.active.set(theme);
    document.documentElement.dataset['theme'] = theme;
  }
}
