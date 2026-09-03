// La única fuente de verdad de los colores de marca para el código JS y de canvas.
// El CSS usa las propiedades personalizadas equivalentes, definidas en :root (index.css).
export const COLORS = {
  abyss: '#0D1117',
  amber: '#D4860A',
  teal: '#00B894',
  coral: '#FF6B35',
  slate: '#94A3B8',
} as const;

/** Tactic colors by index: 0 = Initial Access, 1 = Execution, 2 = Exfiltration */
export const TACTIC_HEX = [COLORS.coral, COLORS.amber, COLORS.teal] as const;

export function hexToRgb(hex: string): [number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

export function hexToRgba(hex: string, alpha: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${alpha.toFixed(3)})`;
}
