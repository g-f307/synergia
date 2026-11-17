import { compareInstants, profileInput, profileInstant, utcInstant } from './profile-time';

describe('Profile time conversion', () => {
  it('uses the profile timezone independently of browser timezone', () => {
    expect(profileInstant('2026-11-01T08:30', 'America/Manaus', 'start')).toBe('2026-11-01T12:30:00Z');
    expect(profileInstant('2026-11-01T08:30', 'Asia/Kolkata', 'start')).toBe('2026-11-01T03:00:00Z');
    expect(profileInput('2026-11-01T12:30:00Z', 'America/Manaus')).toBe('2026-11-01T08:30:00');
  });

  it('includes the last microsecond of a profile calendar day', () => {
    expect(profileInstant('2026-11-01', 'America/Manaus', 'start')).toBe('2026-11-01T04:00:00Z');
    expect(profileInstant('2026-11-01', 'America/Manaus', 'end')).toBe('2026-11-02T03:59:59.999999Z');
    expect(utcInstant('2026-11-01T23:59:59.999999-04:00')).toBe('2026-11-02T03:59:59.999999Z');
  });

  it('handles 23-hour and 25-hour days without assuming a 24-hour duration', () => {
    expect(profileInstant('2026-03-08', 'America/New_York', 'start')).toBe('2026-03-08T05:00:00Z');
    expect(profileInstant('2026-03-08', 'America/New_York', 'end')).toBe('2026-03-09T03:59:59.999999Z');
    expect(profileInstant('2026-11-01', 'America/New_York', 'start')).toBe('2026-11-01T04:00:00Z');
    expect(profileInstant('2026-11-01', 'America/New_York', 'end')).toBe('2026-11-02T04:59:59.999999Z');
  });

  it('starts a day whose local midnight is skipped at the first actual instant', () => {
    expect(profileInstant('2026-09-06', 'America/Santiago', 'start')).toBe('2026-09-06T04:00:00Z');
  });

  it('requires explicit instants for ambiguous or missing local times', () => {
    expect(() => profileInstant('2026-11-01T01:30', 'America/New_York', 'start')).toThrowError(RangeError);
    expect(() => profileInstant('2026-03-08T02:30', 'America/New_York', 'start')).toThrowError(RangeError);
    expect(profileInstant('2026-11-01T01:30:00-04:00', 'America/New_York', 'start')).toBe('2026-11-01T05:30:00Z');
  });

  it('rejects invalid and skipped calendar dates instead of removing their filter', () => {
    expect(() => profileInstant('2026-02-30', 'UTC', 'start')).toThrowError(RangeError);
    expect(() => profileInstant('2011-12-30', 'Pacific/Apia', 'start')).toThrowError(RangeError);
    expect(() => profileInstant('not a date', 'UTC', 'start')).toThrowError(RangeError);
  });

  it('bounds a valid day even when the following civil date was skipped', () => {
    expect(profileInstant('2011-12-29', 'Pacific/Apia', 'start')).toBe('2011-12-29T10:00:00Z');
    expect(profileInstant('2011-12-29', 'Pacific/Apia', 'end')).toBe('2011-12-30T09:59:59.999999Z');
    expect(() => utcInstant('2026-02-30T12:00:00Z')).toThrowError(RangeError);
  });

  it('compares microseconds that JavaScript Date alone would consider equal', () => {
    expect(compareInstants('2026-11-01T12:00:00.000002Z', '2026-11-01T12:00:00.000001Z')).toBe(1);
    expect(compareInstants('2026-11-01T12:00:00Z', '2026-11-01T12:00:00.000000Z')).toBe(0);
  });
});
