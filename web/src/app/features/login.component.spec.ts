import { safeReturnUrl } from './login.component';

describe('safeReturnUrl', () => {
  it('accepts only known internal destinations', () => {
    expect(safeReturnUrl('/executions/exec-1?tab=history')).toBe('/executions/exec-1?tab=history');
    expect(safeReturnUrl('/pending-items')).toBe('/pending-items');
  });

  it('rejects external, protocol-relative and unknown destinations', () => {
    expect(safeReturnUrl('https://example.invalid')).toBe('/profile');
    expect(safeReturnUrl('//example.invalid/path')).toBe('/profile');
    expect(safeReturnUrl('/reports')).toBe('/profile');
  });
});
