import { Indicators, QuantityKey } from '../app/shared/api/operational.models';

export function completeQuantityCoverage(
  values: Record<QuantityKey, number> = { planned: 20, produced: 15, received: 12, released: 10 },
  total = 3
): Indicators['quantities_coverage'] {
  return Object.fromEntries(Object.entries(values).map(([key, value]) => [key, {
    known_sum: value, known_count: total, total_count: total,
    coverage_percent: 100, state: 'complete'
  }])) as Indicators['quantities_coverage'];
}
