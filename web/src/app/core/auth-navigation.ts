const INTERNAL_DESTINATIONS = [
  '/dashboard',
  '/imports',
  '/executions',
  '/search',
  '/workorders',
  '/lots',
  '/serials',
  '/pending-items',
  '/reports',
  '/notifications',
  '/profile',
  '/admin'
];

export function safeReturnUrl(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) {
    return '/profile';
  }

  let decoded: string;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    return '/profile';
  }
  const hasControlCharacter = Array.from(decoded).some((character) => {
    const code = character.charCodeAt(0);
    return code <= 31 || code === 127;
  });
  if (decoded.startsWith('//') || decoded.includes('\\') || hasControlCharacter) {
    return '/profile';
  }

  return INTERNAL_DESTINATIONS.some((path) =>
    value === path || value.startsWith(`${path}/`) || value.startsWith(`${path}?`)
  ) ? value : '/profile';
}
