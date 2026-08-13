// Number formatting for the whole dashboard. Spanish uses a comma for decimals and a dot for
// thousands; mixing "1.435.595" with "81.4%" on the same screen reads as a bug.

export const n = (v: number) => v.toLocaleString('es-AR');

/** Percentage with es-AR decimals. Values that round to zero show "<0,1" instead of "0,0". */
export function pct(value: number, total: number, decimals = 1): string {
  if (!total) return '0';
  const p = (value / total) * 100;
  if (p > 0 && p < 0.1) return '<0,1';
  return p.toLocaleString('es-AR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** One decimal, es-AR. For ratios like "17,5× menos que root". */
export const dec = (v: number, d = 1) =>
  v.toLocaleString('es-AR', { minimumFractionDigits: d, maximumFractionDigits: d });
