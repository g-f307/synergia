import { Injectable, signal } from '@angular/core';

import { AppearancePreferences } from './session.models';

const DEFAULT_APPEARANCE: AppearancePreferences = {
  density: 'comfortable',
  font_scale: 'normal'
};

@Injectable({ providedIn: 'root' })
export class AppearanceService {
  readonly preferences = signal<AppearancePreferences>(DEFAULT_APPEARANCE);

  configure(value?: Partial<AppearancePreferences> | null): void {
    const density = value?.density === 'compact' ? 'compact' : 'comfortable';
    const allowedScales: AppearancePreferences['font_scale'][] = ['small', 'normal', 'large'];
    const candidate = value?.font_scale as AppearancePreferences['font_scale'];
    const fontScale = allowedScales.includes(candidate) ? candidate : 'normal';
    const preferences = { density, font_scale: fontScale } satisfies AppearancePreferences;
    this.preferences.set(preferences);
    document.documentElement.dataset['density'] = preferences.density;
    document.documentElement.dataset['fontScale'] = preferences.font_scale;
  }
}
