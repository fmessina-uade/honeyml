import { useEffect, useRef, useState } from 'react';
import { Play, Pause, RotateCcw, Terminal, ChevronRight } from 'lucide-react';
import type { Replay } from '../lib/api';

// One tactic, one colour, reused across the whole dashboard.
const TACTIC_COLOR: Record<string, string> = {
  Descubrimiento: 'var(--honey-amber)',
  Ejecución: 'var(--agent-coral)',
  Persistencia: 'var(--neural-teal)',
  'Evasión de defensas': '#a78bfa',
};

export function tacticColor(tactic: string): string {
  return TACTIC_COLOR[tactic] ?? 'var(--ghost-slate)';
}

const STEP_MS = 2200;

/**
 * The piece a chart cannot do: a real captured intrusion, replayed command by command,
 * explaining what the attacker was after at each step.
 */
export default function SessionReplay({ replays }: { replays: Replay[] }) {
  const [selected, setSelected] = useState(0);
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const replay = replays[selected];
  const total = replay?.steps.length ?? 0;

  useEffect(() => {
    if (!playing || step >= total) return;
    const id = setTimeout(() => setStep((s) => s + 1), STEP_MS);
    return () => clearTimeout(id);
  }, [playing, step, total]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [step]);

  function pick(i: number) {
    setSelected(i);
    setStep(0);
    setPlaying(true);
  }

  if (!replay) return null;

  const current = replay.steps[Math.min(step, total - 1)];
  const done = step >= total;

  return (
    <section className="grid lg:grid-cols-[1fr_360px] gap-4">
      {/* Terminal */}
      <div className="rounded-xl overflow-hidden ring-1 ring-white/10 bg-[#0f141b]">
        <div className="flex items-center justify-between bg-[#161b22] border-b border-white/5 px-4 py-2.5">
          <div className="flex items-center gap-2 text-[11px] text-white/60">
            <Terminal className="w-3.5 h-3.5" />
            <span className="font-data">
              {replay.attacker}@honeypot · {replay.protocol}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPlaying((p) => !p)}
              className="flex items-center gap-1.5 rounded-md bg-white/5 hover:bg-white/10 px-2.5 py-1 text-[10px] text-white/70 transition"
            >
              {playing ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
              {playing ? 'Pausar' : 'Reproducir'}
            </button>
            <button
              onClick={() => {
                setStep(0);
                setPlaying(true);
              }}
              className="flex items-center gap-1.5 rounded-md bg-white/5 hover:bg-white/10 px-2.5 py-1 text-[10px] text-white/70 transition"
            >
              <RotateCcw className="w-3 h-3" />
              Reiniciar
            </button>
          </div>
        </div>

        <div ref={scrollRef} className="h-[420px] overflow-y-auto p-4 font-data text-[12px]">
          <div className="text-[var(--neural-teal)] mb-3">
            <span className="text-white/40">$</span> ssh {replay.credentials.user}@honeypot
            <div className="text-white/40 mt-1">
              Acceso concedido con {replay.credentials.user}:{replay.credentials.password}
            </div>
          </div>

          {replay.steps.slice(0, step + 1).map((s, i) => (
            <div key={i} className={`mb-3 ${i === step ? 'row-enter' : ''}`}>
              <div className="flex gap-2">
                <span style={{ color: tacticColor(s.tactic) }}>$</span>
                <span className="text-white/85 break-all">{s.command}</span>
              </div>
              {i === step && (
                <div
                  className="mt-1.5 ml-4 pl-3 border-l-2 text-[11px] text-white/55 leading-relaxed"
                  style={{ borderColor: tacticColor(s.tactic) }}
                >
                  {s.what}
                </div>
              )}
            </div>
          ))}

          {done && (
            <div className="text-white/30 mt-4">
              <span className="text-white/40">$</span> sesión finalizada
            </div>
          )}
        </div>

        <div className="border-t border-white/5 px-4 py-2">
          <div className="h-1 rounded bg-white/5 overflow-hidden">
            <div
              className="h-1 rounded transition-all duration-300"
              style={{
                width: `${total ? ((step + 1) / total) * 100 : 0}%`,
                background: tacticColor(current.tactic),
              }}
            />
          </div>
          <div className="flex justify-between mt-1.5 text-[9px] text-white/35">
            <span>
              Paso {Math.min(step + 1, total)} de {total}
            </span>
            <span>{replay.timestamp?.slice(0, 10)}</span>
          </div>
        </div>
      </div>

      {/* Explanation panel: the educational half */}
      <div className="flex flex-col gap-3">
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="flex items-center gap-2 mb-2">
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: tacticColor(current.tactic) }}
            />
            <span className="text-[11px] font-medium" style={{ color: tacticColor(current.tactic) }}>
              {current.tactic}
            </span>
            {current.technique && (
              <span className="font-data text-[10px] text-white/35">[{current.technique}]</span>
            )}
          </div>
          <div className="text-[13px] text-white/85 leading-relaxed mb-3">{current.what}</div>
          <div className="text-[8px] uppercase tracking-wider text-white/30 mb-1">
            Por qué lo hace
          </div>
          <div className="text-[12px] text-white/55 leading-relaxed">{current.why}</div>
        </div>

        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="text-[8px] uppercase tracking-wider text-white/30 mb-2">
            Otras sesiones capturadas
          </div>
          <div className="flex flex-col gap-1">
            {replays.slice(0, 6).map((r, i) => (
              <button
                key={r.attacker + i}
                onClick={() => pick(i)}
                className={`flex items-center justify-between rounded px-2 py-1.5 text-left transition ${
                  i === selected ? 'bg-white/5' : 'hover:bg-white/[0.03]'
                }`}
              >
                <span className="font-data text-[10px] text-white/60">{r.attacker}</span>
                <span className="flex items-center gap-1.5">
                  <span className="text-[9px] text-white/35">{r.steps.length} cmd</span>
                  <ChevronRight className="w-3 h-3 text-white/25" />
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
