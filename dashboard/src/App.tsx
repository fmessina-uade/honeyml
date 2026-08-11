import { useEffect, useState } from 'react';
import { Radar, Terminal, BookOpen, Grid3x3, AlertTriangle } from 'lucide-react';
import { api, type Replay, type Snapshot } from './lib/api';
import Pulse from './components/Pulse';
import SessionReplay from './components/SessionReplay';
import Dictionary from './components/Dictionary';
import MitreMatrix from './components/MitreMatrix';

const SECTIONS = [
  {
    id: 'pulso',
    icon: Radar,
    label: 'El pulso',
    lead: 'Un equipo que nadie publicó en ningún lado, expuesto a internet. Esto es lo que recibe.',
  },
  {
    id: 'anatomia',
    icon: Terminal,
    label: 'Anatomía de un ataque',
    lead: 'Una intrusión real capturada, reproducida paso a paso. Cada comando, explicado.',
  },
  {
    id: 'diccionario',
    icon: BookOpen,
    label: 'Diccionario del atacante',
    lead: 'Qué credenciales prueban y por qué. La evidencia detrás de cada consejo de seguridad.',
  },
  {
    id: 'mitre',
    icon: Grid3x3,
    label: 'Tácticas MITRE',
    lead: 'El marco con el que se clasifica cada acción, iluminado con las capturas propias.',
  },
] as const;

type SectionId = (typeof SECTIONS)[number]['id'];

export default function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [replays, setReplays] = useState<Replay[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<SectionId>('pulso');

  useEffect(() => {
    Promise.all([api.snapshot(), api.replays()])
      .then(([s, r]) => {
        setSnapshot(s);
        setReplays(r);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const section = SECTIONS.find((s) => s.id === active)!;

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 border-r border-white/5 bg-[#0f141b] p-4 flex flex-col">
        <div className="flex items-center gap-2 mb-6">
          <span className="w-7 h-7 rounded-lg bg-[var(--honey-amber)] flex items-center justify-center text-[13px] font-bold text-[#0d1117]">
            H
          </span>
          <div>
            <div className="text-[13px] font-medium text-white font-mono-display">HoneyML</div>
            <div className="text-[9px] text-white/40">Panel educativo</div>
          </div>
        </div>

        <nav className="flex flex-col gap-1">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              onClick={() => setActive(s.id)}
              className={`flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[12px] text-left transition ${
                active === s.id
                  ? 'bg-white/5 text-white/90'
                  : 'text-white/50 hover:text-white/75 hover:bg-white/[0.03]'
              }`}
            >
              <s.icon className="w-3.5 h-3.5 shrink-0" />
              {s.label}
            </button>
          ))}
        </nav>

        <div className="mt-auto pt-4 border-t border-white/5">
          <div className="flex items-center gap-1.5 text-[10px] text-white/40">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--neural-teal)] animate-pulse" />
            Datos reales capturados
          </div>
          {snapshot && (
            <div className="font-data text-[9px] text-white/25 mt-1">
              {snapshot.overview.first_event?.slice(0, 10)} a{' '}
              {snapshot.overview.last_event?.slice(0, 10)}
            </div>
          )}
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 p-6 max-w-[1400px]">
        <header className="mb-5">
          <h1 className="text-xl text-white font-mono-display">{section.label}</h1>
          <p className="text-[13px] text-white/50 mt-1.5 max-w-2xl leading-relaxed">
            {section.lead}
          </p>
        </header>

        {error && (
          <div className="rounded-xl ring-1 ring-[var(--agent-coral)]/30 bg-[var(--agent-coral)]/5 p-4 flex gap-3">
            <AlertTriangle className="w-4 h-4 text-[var(--agent-coral)] shrink-0 mt-0.5" />
            <div>
              <div className="text-[13px] text-white/85">No se pudo cargar la telemetría</div>
              <div className="font-data text-[11px] text-white/45 mt-1">{error}</div>
              <div className="text-[11px] text-white/45 mt-2">
                Verificá que la API esté corriendo: <span className="font-data">make api</span>
              </div>
            </div>
          </div>
        )}

        {!snapshot && !error && <div className="text-white/40 text-[13px]">Cargando…</div>}

        {snapshot && (
          <>
            {active === 'pulso' && (
              <Pulse overview={snapshot.overview} timeline={snapshot.timeline} />
            )}
            {active === 'anatomia' && <SessionReplay replays={replays} />}
            {active === 'diccionario' && (
              <Dictionary
                users={snapshot.credentials.users}
                passwords={snapshot.credentials.passwords}
              />
            )}
            {active === 'mitre' && <MitreMatrix replays={replays} stages={snapshot.stages} />}
          </>
        )}
      </main>
    </div>
  );
}
