import { describe, expect, it } from 'vitest';
import { calculateRendementPercent } from './analyticsMetrics';

describe('calculateRendementPercent', () => {
  it('returns fallback when snapshot is null', () => {
    expect(calculateRendementPercent(null, 'N/A')).toBe('N/A');
  });

  it('returns fallback when total_invested is zero', () => {
    expect(calculateRendementPercent({ total_profit: 10, total_invested: 0 })).toBe('0.0');
  });

  it('returns fallback when total_invested is negative', () => {
    expect(calculateRendementPercent({ total_profit: 10, total_invested: -100 })).toBe('0.0');
  });

  it('calculates rendement when denominator is positive', () => {
    expect(calculateRendementPercent({ total_profit: 25, total_invested: 200 })).toBe('12.5');
  });
});
