import { useI18n } from '../lib/i18n';
import type { Lang } from '../lib/translations';

function FlagAR() {
  return (
    <svg viewBox="0 0 20 14" className="w-5 h-3.5 rounded-[2px]" aria-hidden="true">
      <rect width="20" height="14" fill="#74ACDF" />
      <rect y="4.67" width="20" height="4.66" fill="#fff" />
      <circle cx="10" cy="7" r="1.7" fill="#F6B40E" />
    </svg>
  );
}

// Trece franjas y el cantón azul. A este tamaño las cincuenta estrellas son una trama de puntos:
// dibujadas una por una no se distinguirían y solo ensuciarían el cantón.
const FRANJA = 14 / 13;

function FlagUS() {
  return (
    <svg viewBox="0 0 20 14" className="w-5 h-3.5 rounded-[2px]" aria-hidden="true">
      <rect width="20" height="14" fill="#fff" />
      {Array.from({ length: 7 }, (_, i) => (
        <rect key={i} y={i * 2 * FRANJA} width="20" height={FRANJA} fill="#B22234" />
      ))}
      <rect width="8" height={7 * FRANJA} fill="#3C3B6E" />
      {Array.from({ length: 4 }, (_, fila) =>
        Array.from({ length: 5 }, (_, col) => (
          <circle
            key={`${fila}-${col}`}
            cx={0.9 + col * 1.55}
            cy={0.95 + fila * 1.8}
            r="0.32"
            fill="#fff"
          />
        )),
      )}
    </svg>
  );
}

const ACTIVE_RING: Record<Lang, string> = {
  es: 'ring-1 ring-[#74ACDF] bg-[#74ACDF]/15',
  en: 'ring-1 ring-[#B22234] bg-[#B22234]/15',
};

const OPTIONS: { code: Lang; flag: () => JSX.Element; label: string }[] = [
  { code: 'es', flag: FlagAR, label: 'Español' },
  { code: 'en', flag: FlagUS, label: 'English' },
];

export default function LangToggle() {
  const { lang, setLang } = useI18n();
  return (
    <div
      className="flex items-center gap-1 bg-white/5 border border-white/10 rounded-full p-1 w-fit"
      role="group"
      aria-label="Idioma / Language"
    >
      {OPTIONS.map((opt) => (
        <button
          key={opt.code}
          onClick={() => setLang(opt.code)}
          aria-label={opt.label}
          aria-pressed={lang === opt.code}
          title={opt.label}
          className={`flex items-center justify-center rounded-full px-1.5 py-1 transition-all ${
            lang === opt.code ? ACTIVE_RING[opt.code] : 'opacity-45 hover:opacity-90'
          }`}
        >
          <opt.flag />
        </button>
      ))}
    </div>
  );
}
