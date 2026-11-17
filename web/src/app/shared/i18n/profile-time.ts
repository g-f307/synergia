/** Civil dates belong to the profile timezone, never to the browser timezone. */
function parts(instant: number, timezone: string): number[] {
  const values = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
  }).formatToParts(instant);
  return ['year', 'month', 'day', 'hour', 'minute', 'second'].map(
    key => Number(values.find(part => part.type === key)?.value)
  );
}

function utc(parts: number[]): number {
  const value = new Date(0);
  value.setUTCFullYear(parts[0], parts[1] - 1, parts[2]);
  value.setUTCHours(parts[3] ?? 0, parts[4] ?? 0, parts[5] ?? 0, 0);
  return value.getTime();
}

function civil(value: string): number[] {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?$/.exec(value);
  if (!match) throw new RangeError('invalid_profile_time');
  const result = match.slice(1).map(part => Number(part ?? 0));
  const date = new Date(utc(result));
  if (result[0] < 1 || date.getUTCFullYear() !== result[0] || date.getUTCMonth() + 1 !== result[1]
      || date.getUTCDate() !== result[2] || date.getUTCHours() !== result[3]
      || date.getUTCMinutes() !== result[4] || date.getUTCSeconds() !== result[5]) {
    throw new RangeError('invalid_profile_time');
  }
  return result;
}

function firstInstantOfDay(day: number[], timezone: string, exact = true): number {
  const key = (values: number[]) => values[0] * 10000 + values[1] * 100 + values[2];
  const target = key(day);
  const center = utc(day.slice(0, 3));
  let low = center - 36 * 3600000;
  let high = center + 36 * 3600000;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (key(parts(middle, timezone)) < target) low = middle + 1;
    else high = middle;
  }
  if (exact && key(parts(low, timezone)) !== target) throw new RangeError('invalid_profile_day');
  return low;
}

export function utcInstant(value: string): string {
  const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/i.exec(value);
  if (!match || !Number.isFinite(Date.parse(value))) {
    throw new RangeError('timezone_required');
  }
  civil(match[1]);
  const fraction = (/\.(\d{1,6})(?:Z|[+-]\d{2}:\d{2})$/i.exec(value)?.[1] ?? '').padEnd(6, '0');
  const seconds = new Date(value).toISOString().split('.')[0];
  return `${seconds}${Number(fraction) ? '.' + fraction : ''}Z`;
}

export function profileInstant(value: string | undefined, timezone: string, bound: 'start' | 'end'): string | undefined {
  if (!value) return undefined;
  if (/T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) return utcInstant(value);
  const values = civil(value);
  if (!value.includes('T')) {
    const start = firstInstantOfDay(values, timezone);
    if (bound === 'start') return utcInstant(new Date(start).toISOString());
    const tomorrow = new Date(utc(values.slice(0, 3)) + 86400000);
    // A timezone may skip tomorrow entirely; its next existing day still bounds today.
    const next = firstInstantOfDay([tomorrow.getUTCFullYear(), tomorrow.getUTCMonth() + 1, tomorrow.getUTCDate()], timezone, false);
    // PostgreSQL timestamps have microsecond precision; include the last microsecond.
    const max = Date.parse('9999-12-31T23:59:59.999Z');
    return new Date(Math.min(next - 1, max)).toISOString().replace(/Z$/, '999Z');
  }
  const center = utc(values);
  const candidates = new Set<number>();
  for (let hours = -36; hours <= 36; hours += 6) {
    const sample = center + hours * 3600000;
    const candidate = center - (utc(parts(sample, timezone)) - sample);
    if (parts(candidate, timezone).every((part, index) => part === values[index])) candidates.add(candidate);
  }
  if (candidates.size !== 1) throw new RangeError('ambiguous_or_missing_profile_time');
  return utcInstant(new Date([...candidates][0]).toISOString());
}

export function profileInput(value: string | undefined, timezone: string, dayOnly = false): string {
  if (!value) return '';
  const values = parts(Date.parse(value), timezone);
  const [year, month, day, hour, minute, second] = values.map((part, index) => String(part).padStart(index ? 2 : 4, '0'));
  return dayOnly ? `${year}-${month}-${day}` : `${year}-${month}-${day}T${hour}:${minute}:${second}`;
}

export function compareInstants(left: string, right: string): number {
  const micros = (value: string) => BigInt(Date.parse(value)) * 1000n
    + BigInt((/\.(\d+)Z$/.exec(value)?.[1] ?? '').padEnd(6, '0').slice(3, 6) || '0');
  return micros(left) < micros(right) ? -1 : micros(left) > micros(right) ? 1 : 0;
}
