import ptBR from './catalogs/pt-BR.json';

export const supportedLocales = ['pt-BR', 'en-US'] as const;
export type SupportedLocale = typeof supportedLocales[number];
export type TranslationKey = keyof typeof ptBR;
export type TranslationParameters = Record<string, string | number>;

export function isSupportedLocale(value: string | null | undefined): value is SupportedLocale {
  return supportedLocales.includes(value as SupportedLocale);
}
