import { Injectable, signal } from '@angular/core';

import enUS from './catalogs/en-US.json';
import ptBR from './catalogs/pt-BR.json';
import { SupportedLocale, TranslationKey, TranslationParameters, isSupportedLocale } from './i18n.models';

const DEFAULT_LOCALE: SupportedLocale = 'pt-BR';
const DEFAULT_TIMEZONE = 'America/Manaus';
const catalogs: Record<SupportedLocale, Record<TranslationKey, string>> = {
  'pt-BR': ptBR,
  'en-US': enUS
};

@Injectable({ providedIn: 'root' })
export class I18nService {
  readonly locale = signal<SupportedLocale>(DEFAULT_LOCALE);
  readonly timezone = signal(DEFAULT_TIMEZONE);

  configure(locale: string | null | undefined, timezone?: string | null): void {
    this.locale.set(isSupportedLocale(locale) ? locale : DEFAULT_LOCALE);
    this.timezone.set(timezone?.trim() || DEFAULT_TIMEZONE);
    document.documentElement.lang = this.locale();
  }

  t(key: TranslationKey, parameters: TranslationParameters = {}): string {
    const template = catalogs[this.locale()][key] ?? catalogs[DEFAULT_LOCALE][key];
    return Object.entries(parameters).reduce(
      (message, [name, value]) => message.replaceAll(`{${name}}`, String(value)),
      template
    );
  }

  formatDate(value: string | number | Date, options: Intl.DateTimeFormatOptions = {}): string {
    return new Intl.DateTimeFormat(this.locale(), {
      dateStyle: 'medium',
      timeZone: this.timezone(),
      ...options
    }).format(new Date(value));
  }

  formatNumber(value: number, options: Intl.NumberFormatOptions = {}): string {
    return new Intl.NumberFormat(this.locale(), options).format(value);
  }

  formatQuantity(value: number | null | undefined): string {
    return value == null
      ? this.t('common.notAvailable')
      : this.formatNumber(value, { maximumFractionDigits: 3 });
  }
}
