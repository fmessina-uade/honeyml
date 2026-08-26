import { useEffect, useState } from 'react';
import {
  Radar,
  Terminal,
  BookOpen,
  Grid3x3,
  Network,
  Fingerprint,
  Camera,
  AlertTriangle,
  Archive,
  Users,
  Globe,
} from 'lucide-react';
import {
  api,
  type ArchetypeData,
  type FingerprintData,
  type Health,
  type Replay,
  type Snapshot,
} from './lib/api';
import { useI18n } from './lib/i18n';
import LangToggle from './components/LangToggle';
import Pulse from './components/sections/Pulse';
import SessionReplay from './components/sections/SessionReplay';
import Dictionary from './components/sections/Dictionary';
import MitreMatrix from './components/sections/MitreMatrix';
import Protocols from './components/sections/Protocols';
import Fingerprints from './components/sections/Fingerprints';
import Archetypes from './components/sections/Archetypes';
import Geography from './components/sections/Geography';
import AttackCanvas from './components/AttackCanvas';

// Order is narrative: scale, then one concrete intrusion, then the whole surface, then the
// evidence behind the advice, and finally the formal framework.
const SECTIONS = [
  { id: 'pulso', icon: Radar },
  { id: 'anatomia', icon: Terminal },
  { id: 'protocolos', icon: Network },
  { id: 'diccionario', icon: BookOpen },
  { id: 'huellas', icon: Fingerprint },
  { id: 'arquetipos', icon: Users },
  { id: 'origen', icon: Globe },
  { id: 'mitre', icon: Grid3x3 },
] as const;

type SectionId = (typeof SECTIONS)[number]['id'];

export default function App() {
  const { t } = useI18n();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [replays, setReplays] = useState<Replay[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<SectionId>('pulso');
  const [families, setFamilies] = useState<FingerprintData | null>(null);
  const [archetypes, setArchetypes] = useState<ArchetypeData | null>(null);
  // capture mode freezes every animation so report screenshots are reproducible
  const [capture, setCapture] = useState(false);

  useEffect(() => {
    Promise.all([api.snapshot(), api.replays()])
      .then(([s, r]) => {
        setSnapshot(s);
        setReplays(r);
      })
      .catch((e) => setError(String(e)));
    // separate call: the panel must still load if health is unavailable
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null));
    api
      .fingerprints()
      .then(setFamilies)
      .catch(() => setFamilies(null));
    // Cada uno por separado y con su propio catch: son artefactos generados aparte, y que falte
    // uno no tiene por qué dejar sin panel a los demás.
    api
      .archetypes()
      .then(setArchetypes)
      .catch(() => setArchetypes(null));
  }, []);

  useEffect(() => {
    document.documentElement.dataset.capture = capture ? 'on' : 'off';
  }, [capture]);

  return (
    <div className="h-screen flex overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 border-r border-white/5 bg-[#0f141b] p-4 flex flex-col overflow-y-auto thin-scroll">
        <div className="flex items-center gap-2.5 mb-6">
          <img
            src="/favicon.png"
            alt=""
            aria-hidden
            className="w-8 h-8 rounded-lg shrink-0"
            width={32}
            height={32}
          />
          <div>
            <div className="text-[13px] font-medium text-white font-mono-display">
              {t.brand.name}
            </div>
            <div className="text-[9px] text-white/40">{t.brand.subtitle}</div>
          </div>
        </div>

        <nav className="flex flex-col gap-1">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              onClick={() => setActive(s.id)}
              className={`relative overflow-hidden flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[12px] text-left transition-colors duration-200 ${
                active === s.id
                  ? 'bg-white/5 text-white/90'
                  : 'text-white/50 hover:text-white/75 hover:bg-white/[0.03]'
              }`}
            >
              {active === s.id && (
                <>
                  <span key={`sheen-${s.id}`} className="nav-sheen" aria-hidden />
                  <span
                    className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full"
                    style={{ background: 'var(--honey-amber)' }}
                  />
                </>
              )}
              <s.icon className="w-3.5 h-3.5 shrink-0" />
              {t.nav[s.id]}
            </button>
          ))}
        </nav>

        <div className="mt-auto pt-4 border-t border-white/5 flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <LangToggle />
            <button
              onClick={() => setCapture((c) => !c)}
              title={t.capture.hint}
              aria-pressed={capture}
              /* El modo captura apaga los eventos de puntero de toda la página para que el cursor
                 no deje un estado de hover en la captura. Este botón queda exceptuado, porque si
                 no, no habría forma de volver a apagarlo. */
              data-capture-toggle
              className={`flex items-center justify-center rounded-full p-1.5 transition ${
                capture
                  ? 'bg-[var(--honey-amber)]/20 text-[var(--honey-amber)] ring-1 ring-[var(--honey-amber)]/40'
                  : 'bg-white/5 text-white/35 ring-1 ring-white/10 hover:text-white/70'
              }`}
            >
              <Camera className="w-3.5 h-3.5" />
            </button>
          </div>

          {health?.mode === 'snapshot' ? (
            <div
              className="flex items-start gap-1.5 text-[10px] text-white/40"
              title={`${t.footer.frozenTitle} ${health.generated_at?.slice(0, 16).replace('T', ' ')}`}
            >
              <Archive className="w-3 h-3 shrink-0 mt-[1px] text-[var(--honey-amber)]" />
              <span>
                {t.footer.frozen}
                <span className="block font-data text-[9px] text-white/25">
                  {health.generated_at?.slice(0, 10)}
                </span>
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-[10px] text-white/40">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--neural-teal)] animate-pulse" />
              {t.footer.live}
            </div>
          )}
          {snapshot && (
            <div className="font-data text-[9px] text-white/25 -mt-2">
              {snapshot.overview.first_event?.slice(0, 10)} →{' '}
              {snapshot.overview.last_event?.slice(0, 10)}
            </div>
          )}
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 p-6 max-w-[1400px] overflow-y-auto thin-scroll">
        <header key={`h-${active}`} className="relative mb-5 section-in -mx-6 -mt-6 px-6 pt-6 pb-4">
          {snapshot && <AttackCanvas intensity={snapshot.timeline.map((d) => d.count)} />}
          <div className="relative">
            <h1 className="text-xl text-white font-mono-display">{t.nav[active]}</h1>
            <p className="text-[13px] text-white/50 mt-1.5 max-w-2xl leading-relaxed">
              {t.lead[active]}
            </p>
          </div>
        </header>

        {error && (
          <div className="rounded-xl ring-1 ring-[var(--agent-coral)]/30 bg-[var(--agent-coral)]/5 p-4 flex gap-3">
            <AlertTriangle className="w-4 h-4 text-[var(--agent-coral)] shrink-0 mt-0.5" />
            <div>
              <div className="text-[13px] text-white/85">{t.error.title}</div>
              <div className="font-data text-[11px] text-white/45 mt-1">{error}</div>
              <div className="text-[11px] text-white/45 mt-2">
                {t.error.hint} <span className="font-data">make api</span>
              </div>
            </div>
          </div>
        )}

        {/* Skeleton rather than a spinner: the snapshot runs several aggregations over 1,9 M
            documents and takes a beat, and a layout that does not jump reads as deliberate. */}
        {!snapshot && !error && (
          <div className="flex flex-col gap-3 animate-pulse">
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-[104px] rounded-xl bg-white/[0.03] ring-1 ring-white/5" />
              ))}
            </div>
            <div className="h-[196px] rounded-xl bg-white/[0.03] ring-1 ring-white/5" />
          </div>
        )}

        {snapshot && (
          <div key={active} className="section-in">
            {active === 'pulso' && (
              <Pulse
                overview={snapshot.overview}
                timeline={snapshot.timeline}
                hourly={snapshot.hourly}
                weekly={snapshot.weekly_rhythm}
              />
            )}
            {active === 'anatomia' && <SessionReplay replays={replays} />}
            {active === 'diccionario' && (
              <Dictionary
                users={snapshot.credentials.users}
                passwords={snapshot.credentials.passwords}
              />
            )}
            {active === 'protocolos' && <Protocols detail={snapshot.protocol_detail} />}
            {active === 'huellas' &&
              (families ? (
                <Fingerprints data={families} />
              ) : (
                <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-8 text-center text-[13px] text-white/50">
                  {t.error.title}
                </div>
              ))}
            {active === 'arquetipos' &&
              (archetypes ? (
                <Archetypes data={archetypes} />
              ) : (
                <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-8 text-center text-[13px] text-white/50">
                  {t.error.title}
                </div>
              ))}
            {active === 'origen' &&
              (snapshot.geography ? (
                <Geography data={snapshot.geography} />
              ) : (
                <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-8 text-center text-[13px] text-white/50">
                  {t.error.title}
                </div>
              ))}
            {active === 'mitre' && <MitreMatrix replays={replays} stages={snapshot.stages} />}
          </div>
        )}
      </main>
    </div>
  );
}
