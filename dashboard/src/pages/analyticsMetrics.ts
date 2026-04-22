interface CapitalSnapshot {
  total_profit?: number | null;
  total_invested?: number | null;
}

export const DEFAULT_RENDEMENT_FALLBACK = '0.0';

export function calculateRendementPercent(
  capitalData: CapitalSnapshot | null | undefined,
  fallback: string = DEFAULT_RENDEMENT_FALLBACK
): string {
  const totalInvested = Number(capitalData?.total_invested ?? 0);
  const totalProfit = Number(capitalData?.total_profit ?? 0);

  if (!Number.isFinite(totalInvested) || totalInvested <= 0) {
    return fallback;
  }

  if (!Number.isFinite(totalProfit)) {
    return fallback;
  }

  return ((totalProfit / totalInvested) * 100).toFixed(1);
}
