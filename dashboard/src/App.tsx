import { useEffect, useRef, useState } from 'react';
import {
  Radar,
  Terminal,
  BookOpen,
  Grid3x3,
  Network,
  Fingerprint,
  AlertTriangle,
  Archive,
  Users,
  Globe,
  ShieldCheck,
  LayoutDashboard,
  Menu,
  X,
  type LucideIcon,
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
import Preferencias from './components/Preferencias';
import Descifrado from './components/Descifrado';
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

// Dos grupos. Arriba lo que se opera: el resumen de todo y el motor, que es lo que distingue al
// proyecto. Abajo lo que se aprende, en orden narrativo: primero la escala, después una intrusión
// concreta, después toda la superficie, la evidencia detrás del consejo y al final el marco formal.
const GRUPOS = [
  {
    id: 'operacion',
    secciones: [
      { id: 'inicio', icon: LayoutDashboard },
      { id: 'triaje', icon: ShieldCheck },
    ],
  },
  {
    id: 'aprender',
    secciones: [
      { id: 'pulso', icon: Radar },
      { id: 'anatomia', icon: Terminal },
      { id: 'protocolos', icon: Network },
      { id: 'diccionario', icon: BookOpen },
      { id: 'huellas', icon: Fingerprint },
      { id: 'arquetipos', icon: Users },
      { id: 'origen', icon: Globe },
      { id: 'mitre', icon: Grid3x3 },
    ],
  },
] as const satisfies readonly {
  id: string;
  secciones: readonly { id: string; icon: LucideIcon }[];
}[];

export type SectionId = (typeof GRUPOS)[number]['secciones'][number]['id'];

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
  const [menuAbierto, setMenuAbierto] = useState(false);
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

  // El menú del teléfono se cierra con Escape, como cualquier diálogo.
  useEffect(() => {
    if (!menuAbierto) return;
    const alTeclear = (e: KeyboardEvent) => e.key === 'Escape' && setMenuAbierto(false);
    document.addEventListener('keydown', alTeclear);
    return () => document.removeEventListener('keydown', alTeclear);
  }, [menuAbierto]);

  const ir = (id: SectionId) => {
    setActive(id);
    setMenuAbierto(false);
  };

  const marca = (
    <div className="flex items-center gap-2.5">
      <img
        src="/favicon.png"
        alt=""
        aria-hidden
        className="w-8 h-8 rounded-lg shrink-0"
        width={32}
        height={32}
      />
      <div>
        <div className="text-[13px] text-white font-mono-display">{t.brand.name}</div>
        <div className="text-[9px] text-white/40">{t.brand.subtitle}</div>
      </div>
    </div>
  );

  const navegacion = (
    <nav className="flex flex-col gap-4" aria-label={t.brand.name}>
      {GRUPOS.map((grupo) => (
        <div key={grupo.id} className="flex flex-col gap-1">
          <div className="rotulo px-2.5 mb-1">{t.navGroups[grupo.id]}</div>
          {grupo.secciones.map((s) => (
            <button
              key={s.id}
              onClick={() => ir(s.id)}
              aria-current={active === s.id ? 'page' : undefined}
              className={`relative overflow-hidden flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[12px] text-left transition-colors duration-200 ${
                active === s.id
                  ? 'nav-activa bg-white/5 text-white/90'
                  : 'text-white/55 hover:text-white/80 hover:bg-white/[0.03]'
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
        </div>
      ))}
    </nav>
  );

  const estado =
    health?.mode === 'snapshot' ? (
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
    );

  const rango = snapshot && (
    <div className="font-data text-[9px] text-white/25 -mt-2">
      {t.footer.range(
        snapshot.overview.first_event?.slice(0, 10) ?? '',
        snapshot.overview.last_event?.slice(0, 10) ?? '',
      )}
    </div>
  );

  return (
    <div className="h-[100dvh] flex flex-col md:flex-row overflow-hidden">
      {/* En pantallas angostas la barra lateral se vuelve una barra de arriba con un menú que se
          despliega desde el costado. */}
      <header className="tapa md:hidden shrink-0 border-b border-white/5 bg-barra">
        <div className="flex items-center justify-between gap-3 px-4 py-2.5">
          {marca}
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-white/60 truncate max-w-[40vw]">{t.nav[active]}</span>
            <button
              onClick={() => setMenuAbierto(true)}
              aria-label={t.menu.open}
              aria-expanded={menuAbierto}
              data-capture-toggle
              className="flex items-center justify-center w-9 h-9 rounded-lg ring-1 ring-white/10 text-white/75 hover:text-white"
            >
              <Menu className="w-[18px] h-[18px]" />
            </button>
          </div>
        </div>
      </header>

      {menuAbierto && (
        <div className="md:hidden fixed inset-0 z-50" role="dialog" aria-modal="true">
          {/* El velo, el botón de cerrar y el de captura quedan exceptuados del modo captura: si
              no, con el modo prendido no habría forma de volver a apagarlo desde el teléfono. */}
          <button
            aria-label={t.menu.close}
            onClick={() => setMenuAbierto(false)}
            data-capture-toggle
            className="absolute inset-0 bg-black/55 menu-velo"
          />
          <div className="tapa menu-cajon absolute inset-y-0 left-0 w-[84%] max-w-[300px] bg-barra ring-1 ring-white/10 p-4 flex flex-col gap-5 overflow-y-auto thin-scroll">
            <div className="flex items-center justify-between">
              {marca}
              <button
                onClick={() => setMenuAbierto(false)}
                aria-label={t.menu.close}
                data-capture-toggle
                className="flex items-center justify-center w-8 h-8 rounded-lg text-white/60 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            {navegacion}
            <div className="mt-auto pt-4 border-t border-white/5 flex flex-col gap-3">
              <Preferencias capture={capture} onCapture={() => setCapture((c) => !c)} />
              {estado}
              {rango}
            </div>
          </div>
        </div>
      )}

      <aside className="tapa hidden md:flex w-56 shrink-0 border-r border-white/5 bg-barra p-4 flex-col overflow-y-auto thin-scroll">
        <div className="mb-6">{marca}</div>
        {navegacion}
        <div className="mt-auto pt-4 border-t border-white/5 flex flex-col gap-3">
          <Preferencias capture={capture} onCapture={() => setCapture((c) => !c)} />
          {estado}
          {rango}
        </div>
      </aside>

      <main
        ref={principal}
        className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden thin-scroll papel"
      >
        <div className="max-w-[1400px] p-4 md:p-6">
          <header
            key={`h-${active}`}
            className="relative mb-5 section-in -mx-4 -mt-4 px-4 pt-4 pb-4 md:-mx-6 md:-mt-6 md:px-6 md:pt-6"
          >
            {snapshot && <AttackCanvas intensity={snapshot.timeline.map((d) => d.count)} />}
            <div className="relative">
              <h1 className="text-lg md:text-xl text-white font-mono-display">
                <span className="titulo-seccion inline-block">
                  <Descifrado texto={t.nav[active]} />
                </span>
              </h1>
              <p className="text-[13px] text-white/55 mt-1.5 max-w-2xl leading-relaxed">
                {t.lead[active]}
              </p>
            </div>
          </header>

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
                  onIr={ir}
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
        </div>
      </main>
    </div>
  );
}
