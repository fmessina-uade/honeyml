import { useCallback, useEffect, useRef, useState } from 'react';
import { Play, Pause, RotateCcw, Terminal, Gauge } from 'lucide-react';
import type { Replay } from '../../lib/api';

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

const SPEEDS = [
  { label: '0,5×', ms: 4400 },
  { label: '1×', ms: 2200 },
  { label: '2×', ms: 1100 },
];

/**
 * The piece a chart cannot do: a real captured intrusion, replayed command by command,
 * explaining what the attacker was after at each step.
 *
 * Playback is scrubbable and keyboard-driven. Someone reading this wants to stop on a command
 * and re-read it, and autoplay alone makes that a race against the timer.
 */
export default function SessionReplay({ replays }: { replays: Replay[] }) {
  const [selected, setSelected] = useState(0);
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);
  const scrollRef = useRef<HTMLDivElement>(null);

  const replay = replays[selected];
  const total = replay?.steps.length ?? 0;

  useEffect(() => {
    if (!playing || step >= total) return;
    const id = setTimeout(() => setStep((s) => s + 1), SPEEDS[speed].ms);
    return () => clearTimeout(id);
  }, [playing, step, total, speed]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [step]);

  const seek = useCallback(
    (to: number) => {
      setStep(Math.max(0, Math.min(to, total - 1)));
      setPlaying(false);
    },
    [total],
  );

  // Space toggles, arrows step. Scoped to the section so it never hijacks the whole page.
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === ' ') {
      e.preventDefault();
      setPlaying((p) => !p);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      seek(step + 1);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      seek(step - 1);
    }
  };

  function pick(i: number) {
    setSelected(i);
    setStep(0);
    setPlaying(true);
  }

  if (!replay) {
    return (
      <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-8 text-center">
        <div className="text-[13px] text-white/60">No hay sesiones con comandos para reproducir.</div>
        <div className="text-[11px] text-white/35 mt-1">
          Generalas con <span className="font-data">make replays</span> después de bajar logs frescos.
        </div>
      </div>
    );
  }

  const current = replay.steps[Math.min(step, total - 1)];
  const done = step >= total - 1;

  return (
    <section
      className="grid lg:grid-cols-[1fr_360px] gap-4 outline-none"
      tabIndex={0}
      onKeyDown={onKeyDown}
    >
      {/* Terminal */}
      <div className="rounded-xl overflow-hidden ring-1 ring-white/10 bg-[#0f141b]">
        <div className="flex items-center justify-between bg-[#161b22] border-b border-white/5 px-4 py-2.5 gap-2 flex-wrap">
          <div className="flex items-center gap-2 text-[11px] text-white/60">
            <Terminal className="w-3.5 h-3.5" />
            <span className="font-data">
              {replay.attacker}@honeypot · {replay.protocol}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center rounded-md bg-white/5 p-0.5">
              <Gauge className="w-3 h-3 text-white/30 mx-1" />
              {SPEEDS.map((s, i) => (
                <button
                  key={s.label}
                  onClick={() => setSpeed(i)}
                  className={`rounded px-1.5 py-0.5 text-[9px] font-data transition ${
                    i === speed ? 'bg-white/10 text-white/85' : 'text-white/40 hover:text-white/70'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
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

        <div
          ref={scrollRef}
          className="thin-scroll h-[420px] overflow-y-auto p-4 font-data text-[12px]"
        >
          <div className="text-[var(--neural-teal)] mb-3">
            <span className="text-white/40">$</span> ssh {replay.credentials.user}@honeypot
            <div className="text-white/40 mt-1">
              Acceso concedido con {replay.credentials.user}:{replay.credentials.password}
            </div>
          </div>

          {replay.steps.slice(0, step + 1).map((s, i) => (
            <div key={i} className={`mb-3 ${i === step ? 'row-enter' : ''}`}>
              <button
                onClick={() => seek(i)}
                className="flex gap-2 text-left w-full group"
                title="Ir a este paso"
              >
                <span style={{ color: tacticColor(s.tactic) }}>$</span>
                <span
                  className={`break-all transition-colors ${
                    i === step ? 'text-white/90' : 'text-white/45 group-hover:text-white/70'
                  }`}
                >
                  {s.command}
                </span>
              </button>
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

          {/* the cursor is what makes it read as a live terminal rather than a code block */}
          <div className="flex gap-2">
            <span className="text-white/40">$</span>
            {done && !playing ? (
              <span className="text-white/30">sesión finalizada</span>
            ) : (
              <span className="terminal-cursor" />
            )}
          </div>
        </div>

        {/* scrubbable progress: click anywhere to jump to that command */}
        <div className="border-t border-white/5 px-4 py-2">
          <input
            type="range"
            min={0}
            max={Math.max(total - 1, 0)}
            value={Math.min(step, total - 1)}
            onChange={(e) => seek(Number(e.target.value))}
            aria-label="Posición en la sesión"
            className="w-full h-1 appearance-none bg-transparent cursor-pointer
                       [&::-webkit-slider-runnable-track]:h-1 [&::-webkit-slider-runnable-track]:rounded
                       [&::-webkit-slider-runnable-track]:bg-white/8
                       [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-2.5
                       [&::-webkit-slider-thumb]:h-2.5 [&::-webkit-slider-thumb]:rounded-full
                       [&::-webkit-slider-thumb]:-mt-[3px] [&::-webkit-slider-thumb]:transition-transform
                       hover:[&::-webkit-slider-thumb]:scale-125"
            style={
              {
                '--c': tacticColor(current.tactic),
                background: `linear-gradient(to right, ${tacticColor(current.tactic)} ${
                  total > 1 ? (step / (total - 1)) * 100 : 100
                }%, rgba(255,255,255,0.08) 0)`,
                borderRadius: 4,
              } as React.CSSProperties
            }
          />
          <div className="flex justify-between mt-1.5 text-[9px] text-white/35">
            <span>
              Paso {Math.min(step + 1, total)} de {total}
              <span className="text-white/20 ml-2 hidden sm:inline">
                espacio pausa · ← → paso a paso
              </span>
            </span>
            <span>{replay.timestamp?.slice(0, 10)}</span>
          </div>
        </div>
      </div>

      {/* Explanation panel: the educational half */}
      <div className="flex flex-col gap-3">
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: tacticColor(current.tactic) }}
            />
            <span className="text-[11px] font-medium" style={{ color: tacticColor(current.tactic) }}>
              {current.tactic}
            </span>
            {current.technique && (
              <a
                href={`https://attack.mitre.org/techniques/${current.technique.replace('.', '/')}/`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-data text-[10px] text-white/35 hover:text-[var(--honey-amber)] transition underline decoration-dotted underline-offset-2"
                title="Ver la técnica en MITRE ATT&CK"
              >
                [{current.technique}]
              </a>
            )}
          </div>
          <div key={step} className="section-in">
            <div className="text-[13px] text-white/85 leading-relaxed mb-3">{current.what}</div>
            <div className="text-[8px] uppercase tracking-wider text-white/30 mb-1">
              Por qué lo hace
            </div>
            <div className="text-[12px] text-white/55 leading-relaxed">{current.why}</div>
          </div>
        </div>

        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-[8px] uppercase tracking-wider text-white/30">
              Otras sesiones capturadas
            </span>
            <span className="font-data text-[9px] text-white/25">{replays.length} atacantes</span>
          </div>
          <div className="thin-scroll flex flex-col gap-1 max-h-[260px] overflow-y-auto pr-1">
            {replays.map((r, i) => (
              <button
                key={r.attacker + i}
                onClick={() => pick(i)}
                className={`rounded px-2 py-1.5 text-left transition ${
                  i === selected
                    ? 'bg-white/[0.07] ring-1 ring-white/10'
                    : 'hover:bg-white/[0.04] ring-1 ring-transparent'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={`font-data text-[10px] ${
                      i === selected ? 'text-white/85' : 'text-white/55'
                    }`}
                  >
                    {r.attacker}
                  </span>
                  <span className="font-data text-[9px] text-white/30 shrink-0">
                    {r.credentials.user}:{r.credentials.password}
                  </span>
                </div>
                {/* the tactic strip is what distinguishes one bot from another at a glance */}
                <div className="flex items-center gap-1 mt-1.5">
                  {r.tactics.map((t) => (
                    <span
                      key={t}
                      title={t}
                      className="h-1 flex-1 rounded-full"
                      style={{ background: tacticColor(t), opacity: i === selected ? 0.95 : 0.4 }}
                    />
                  ))}
                  <span className="text-[9px] text-white/25 ml-1 shrink-0">{r.steps.length} cmd</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
