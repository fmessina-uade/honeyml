import { useI18n } from '../lib/i18n';
import type { Lang } from '../lib/translations';

// Same flags as the public site, so the control reads as the same product.
function FlagAR() {
  return (
    <svg viewBox="0 0 20 14" className="w-5 h-3.5 rounded-[2px]" aria-hidden="true">
      <rect width="20" height="14" fill="#74ACDF" />
      <rect y="4.67" width="20" height="4.66" fill="#fff" />
      <circle cx="10" cy="7" r="1.7" fill="#F6B40E" />
    </svg>
  );
}

function FlagGB() {
  return (
    <svg viewBox="0 0 20 14" className="w-5 h-3.5 rounded-[2px]" aria-hidden="true">
      <rect width="20" height="14" fill="#012169" />
      <path d="M0 0l20 14M20 0L0 14" stroke="#fff" strokeWidth="2.8" />
      <path d="M0 0l20 14M20 0L0 14" stroke="#C8102E" strokeWidth="1.2" />
      <rect x="8.3" width="3.4" height="14" fill="#fff" />
      <rect y="5.3" width="20" height="3.4" fill="#fff" />
      <rect x="9.1" width="1.8" height="14" fill="#C8102E" />
      <rect y="6.1" width="20" height="1.8" fill="#C8102E" />
    </svg>
  );
}

const ACTIVE_RING: Record<Lang, string> = {
  es: 'ring-1 ring-[#74ACDF] bg-[#74ACDF]/15',
  en: 'ring-1 ring-[#C8102E] bg-[#C8102E]/15',
};

const OPTIONS: { code: Lang; flag: () => JSX.Element; label: string }[] = [
  { code: 'es', flag: FlagAR, label: 'Español' },
  { code: 'en', flag: FlagGB, label: 'English' },
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
