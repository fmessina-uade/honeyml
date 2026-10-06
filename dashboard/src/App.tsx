import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Archive } from 'lucide-react';
import {
  api,
  type ArchetypeData,
  type FingerprintData,
  type Health,
  type Replay,
  type Snapshot,
} from './lib/api';
import { useI18n } from './lib/i18n';
import Preferencias from './components/Preferencias';
import BarraSuperior from './components/BarraSuperior';
import Titular from './components/Titular';
import { lecciones, type SectionId } from './components/lecciones';
import Inicio from './components/sections/Inicio';
import Pulse from './components/sections/Pulse';
import SessionReplay from './components/sections/SessionReplay';
import Dictionary from './components/sections/Dictionary';
import MitreMatrix from './components/sections/MitreMatrix';
import Protocols from './components/sections/Protocols';
import Fingerprints from './components/sections/Fingerprints';
import Archetypes from './components/sections/Archetypes';
import Geography from './components/sections/Geography';
import Triage from './components/sections/Triage';
import AttackCanvas from './components/AttackCanvas';

export type { SectionId };

const PRESENTACION_PROPIA = new Set<SectionId>([
  'inicio',
  'pulso',
  'protocolos',
  'origen',
  'diccionario',
  'huellas',
  'arquetipos',
  'anatomia',
  'mitre',
]);

function SinDatos() {
  const { t } = useI18n();
  return <div className="panel p-8 text-center text-[13px] text-white/50">{t.error.title}</div>;
}

export default function App() {
  const { t } = useI18n();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [replays, setReplays] = useState<Replay[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<SectionId>('inicio');
  const [families, setFamilies] = useState<FingerprintData | null>(null);
  const [archetypes, setArchetypes] = useState<ArchetypeData | null>(null);
  // el modo captura congela todas las animaciones, así las capturas de pantalla se repiten igual
  const [capture, setCapture] = useState(false);
  const principal = useRef<HTMLElement>(null);

  useEffect(() => {
    Promise.all([api.snapshot(), api.replays()])
      .then(([s, r]) => {
        setSnapshot(s);
        setReplays(r);
      })
      .catch((e) => setError(String(e)));
    // llamada aparte: el panel tiene que cargar igual si el chequeo de salud no responde
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

  // Un único oyente para el filo de todas las tarjetas: cada una sabe dónde está el puntero por
  // dos variables de CSS, sin un manejador por tarjeta.
  useEffect(() => {
    const mover = (e: PointerEvent) => {
      const tarjeta = (e.target as Element | null)?.closest?.('.panel') as HTMLElement | null;
      if (!tarjeta) return;
      const r = tarjeta.getBoundingClientRect();
      tarjeta.style.setProperty('--mx', `${e.clientX - r.left}px`);
      tarjeta.style.setProperty('--my', `${e.clientY - r.top}px`);
    };
    document.addEventListener('pointermove', mover, { passive: true });
    return () => document.removeEventListener('pointermove', mover);
  }, []);

  // Al cambiar de sección se vuelve arriba: si no, en el teléfono la sección nueva abre por la
  // mitad, a la altura donde había quedado la anterior.
  useEffect(() => {
    principal.current?.scrollTo({ top: 0 });
  }, [active]);

  const cifras = useMemo(
    () => (snapshot ? lecciones(snapshot, families, archetypes, replays.length, t) : null),
    [snapshot, families, archetypes, replays.length, t],
  );

  const desde = snapshot?.overview.first_event?.slice(0, 10) ?? '';
  const hasta = snapshot?.overview.last_event?.slice(0, 10) ?? '';
  const estado =
    health?.mode === 'snapshot' ? (
      <span
        className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] text-white/55 ring-1 ring-white/10 bg-white/[0.03] whitespace-nowrap"
        title={`${t.footer.frozenTitle} ${health.generated_at?.slice(0, 16).replace('T', ' ')}`}
      >
        <Archive className="w-3 h-3 shrink-0 text-[var(--honey-amber)]" />
        {t.footer.frozenShort}
      </span>
    ) : (
      <span
        className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] text-white/55 ring-1 ring-white/10 bg-white/[0.03] whitespace-nowrap"
        title={snapshot ? t.footer.range(desde, hasta) : undefined}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--neural-teal)] animate-pulse" />
        {t.footer.liveShort}
      </span>
    );

  return (
    <div className="h-[100dvh] flex flex-col overflow-hidden">
      <BarraSuperior
        active={active}
        onIr={setActive}
        snapshot={snapshot}
        familias={families}
        arquetipos={archetypes}
        cifras={cifras}
        estado={estado}
        preferencias={<Preferencias capture={capture} onCapture={() => setCapture((c) => !c)} />}
      />

      <main
        ref={principal}
        className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden thin-scroll papel"
      >
        <div className="max-w-[1320px] mx-auto px-4 md:px-8 pb-12">
          {/* Las secciones con presentación propia dibujan su encabezado; el resto usa este. */}
          {!(PRESENTACION_PROPIA.has(active) && snapshot) && (
            <header key={`h-${active}`} className="relative -mx-4 px-4 md:-mx-8 md:px-8 pt-8 pb-7">
              {snapshot && <AttackCanvas intensity={snapshot.timeline.map((d) => d.count)} />}
              <div className="relative max-w-3xl">
                <Titular texto={t.nav[active]} />
                <p className="text-[14px] text-white/55 mt-3 leading-relaxed section-in">
                  {t.lead[active]}
                </p>
              </div>
            </header>
          )}

          {error && (
            <div className="rounded-xl ring-1 ring-[var(--agent-coral)]/30 bg-[var(--agent-coral)]/5 p-4 flex gap-3">
              <AlertTriangle className="w-4 h-4 text-[var(--agent-coral)] shrink-0 mt-0.5" />
              <div className="min-w-0">
                <div className="text-[13px] text-white/85">{t.error.title}</div>
                <div className="font-data text-[11px] text-white/45 mt-1 break-all">{error}</div>
                <div className="text-[11px] text-white/45 mt-2">
                  {t.error.hint} <span className="font-data">make api</span>
                </div>
              </div>
            </div>
          )}

          {/* Un esqueleto en lugar de un indicador que gira: el snapshot hace varias agregaciones
              sobre todo el corpus y tarda un momento, y una grilla que no salta al llegar los
              datos se lee como hecha a propósito. */}
          {!snapshot && !error && (
            <div className="flex flex-col gap-3 animate-pulse">
              <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="h-[104px] panel" />
                ))}
              </div>
              <div className="h-[196px] panel" />
            </div>
          )}

          {snapshot && (
            <div key={active} className="section-in">
              {active === 'inicio' && (
                <Inicio
                  snapshot={snapshot}
                  familias={families}
                  arquetipos={archetypes}
                  sesiones={replays.length}
                  onIr={setActive}
                />
              )}
              {active === 'triaje' && <Triage />}
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
              {active === 'huellas' && (families ? <Fingerprints data={families} /> : <SinDatos />)}
              {active === 'arquetipos' &&
                (archetypes ? <Archetypes data={archetypes} /> : <SinDatos />)}
              {active === 'origen' &&
                (snapshot.geography ? <Geography data={snapshot.geography} /> : <SinDatos />)}
              {active === 'mitre' && (
                <MitreMatrix
                  replays={replays}
                  stages={snapshot.stages}
                  overview={snapshot.overview}
                />
              )}
            </div>
          )}

          {snapshot && (
            <footer className="mt-12 pt-5 border-t border-white/5 flex flex-wrap items-center justify-between gap-3 text-[11px] text-white/35">
              <span className="flex items-center gap-2">
                <img src="/favicon.png" alt="" aria-hidden className="w-4 h-4 rounded" />
                <span className="font-mono-display">{t.brand.name}</span>
                <span className="geist text-[12px] text-white/40">{t.brand.subtitle}</span>
              </span>
              <span className="font-data">{t.footer.range(desde, hasta)}</span>
            </footer>
          )}
        </div>
      </main>
      <div className="grano" aria-hidden />
    </div>
  );
}
