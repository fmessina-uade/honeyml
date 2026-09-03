// El formateo de números de todo el panel.
//
// El locale sigue al selector de idioma: en español se escribe 1.854.605 y 1,6, y en inglés
// 1,854,605 y 1.6. Mezclarlos en una misma pantalla se lee como un error, y dejar es-AR fijo hacía
// que la vista en inglés mostrara decimales a la española.
//
// El locale vigente vive en el ámbito del módulo en lugar de ir pasando por cada llamada: hay
// exactamente uno, lo maneja el proveedor de idioma, y la alternativa es una prop en cada número
// del panel.

let locale: 'es-AR' | 'en-GB' = 'es-AR';

/** La llama el proveedor de idioma cada vez que el idioma cambia. */
export function setNumberLocale(lang: 'es' | 'en'): void {
  locale = lang === 'en' ? 'en-GB' : 'es-AR';
}

export const n = (v: number) => v.toLocaleString(locale);

/** Porcentaje en el locale activo. Los valores que redondean a cero muestran "<0,1" y no "0,0". */
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
