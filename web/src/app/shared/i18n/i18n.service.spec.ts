import { TestBed } from '@angular/core/testing';

import { I18nService } from './i18n.service';

describe('I18nService', () => {
  let service: I18nService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(I18nService);
    service.configure('pt-BR', 'America/Manaus');
  });

  it('uses Brazilian Portuguese as the safe fallback', () => {
    service.configure('es-ES', 'UTC');

    expect(service.locale()).toBe('pt-BR');
    expect(document.documentElement.lang).toBe('pt-BR');
    expect(service.t('auth.submit')).toBe('Entrar');
  });

  it('switches to English without changing application state', () => {
    service.configure('en-US', 'UTC');

    expect(service.t('auth.submit')).toBe('Sign in');
    expect(document.documentElement.lang).toBe('en-US');
  });

  it('formats dates, numbers and absent quantities by locale', () => {
    expect(service.formatNumber(1234.5)).toBe('1.234,5');
    expect(service.formatDate('2026-01-02T12:00:00Z')).toContain('2 de jan. de 2026');
    expect(service.formatDate('2026-01-02T12:00:00Z', { timeStyle: 'short' })).toContain('08:00');
    expect(service.formatQuantity(null)).toBe('Não informado');
    expect(service.formatQuantity(0)).toBe('0');

    service.configure('en-US', 'UTC');
    expect(service.formatNumber(1234.5)).toBe('1,234.5');
    expect(service.formatDate('2026-01-02T12:00:00Z', { timeStyle: 'short' })).toContain('12:00 PM');
    expect(service.formatQuantity(12.5)).toBe('12.5');
  });
});
