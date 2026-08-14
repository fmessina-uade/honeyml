// Number formatting for the whole dashboard.
//
// The locale follows the language toggle: Spanish writes 1.854.605 and 1,6, English writes
// 1,854,605 and 1.6. Mixing them on one screen reads as a bug, and hardcoding es-AR made the
// English view render Spanish decimals.
//
// The current locale lives at module scope rather than being threaded through every call site:
// there is exactly one of it, the provider owns it, and the alternative is a prop on every
// number in the panel.

let locale: 'es-AR' | 'en-GB' = 'es-AR';

/** Called by the language provider whenever the language changes. */
export function setNumberLocale(lang: 'es' | 'en'): void {
  locale = lang === 'en' ? 'en-GB' : 'es-AR';
}

export const n = (v: number) => v.toLocaleString(locale);

/** Percentage in the active locale. Values that round to zero show "<0,1" instead of "0,0". */
export function pct(value: number, total: number, decimals = 1): string {
  if (!total) return '0';
  const p = (value / total) * 100;
  if (p > 0 && p < 0.1) {
    return `<${(0.1).toLocaleString(locale, { minimumFractionDigits: 1 })}`;
  }
  return p.toLocaleString(locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** One decimal, active locale. For ratios like "17,5× menos que root". */
export const dec = (v: number, d = 1) =>
  v.toLocaleString(locale, { minimumFractionDigits: d, maximumFractionDigits: d });
