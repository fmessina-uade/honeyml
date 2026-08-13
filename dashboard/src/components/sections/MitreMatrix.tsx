import type { Bucket, Replay } from '../../lib/api';
import { tacticColor } from './SessionReplay';
import Reveal from '../Reveal';
import Tooltip, { useTooltip } from '../Tooltip';
import { n, pct } from '../../lib/format';

// The framework itself is part of the lesson: what each tactic means in plain language.
const TACTIC_MEANING: Record<string, string> = {
  Descubrimiento:
    'El atacante averigua dónde entró: qué sistema es, qué permisos tiene, qué hay instalado.',
  Ejecución: 'Corre código propio en el equipo, normalmente después de descargarlo.',
  Persistencia: 'Se asegura de seguir dentro aunque se reinicie el equipo o se cambie la clave.',
  'Evasión de defensas': 'Borra rastros y evita las herramientas que podrían detectarlo.',
};

/**
 * MITRE ATT&CK tactics lit up with the project's own captures. Teaches the framework using
 * evidence the reader just saw in the replay, instead of an abstract table.
 */
export default function MitreMatrix({
  replays,
  stages,
}: {
  replays: Replay[];
  stages: Bucket[];
}) {
  // count how many captured sessions touched each tactic
  const counts = new Map<string, number>();
  for (const r of replays) {
    for (const t of r.tactics) counts.set(t, (counts.get(t) ?? 0) + 1);
  }
  const tip = useTooltip();
  const tactics = Object.keys(TACTIC_MEANING);
  const maxSessions = Math.max(...tactics.map((t) => counts.get(t) ?? 0), 1);

  return (
    <section className="flex flex-col gap-4">
      <Tooltip content={tip.content} at={tip.at} />
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {tactics.map((t, idx) => {
          const n = counts.get(t) ?? 0;
          const active = n > 0;
          return (
            <Reveal key={t} delay={idx * 90}>
            <div
              className="rounded-xl p-4 ring-1 transition h-full"
              style={{
                background: active ? `${tacticColor(t)}12` : 'rgba(255,255,255,0.02)',
                borderColor: 'transparent',
                boxShadow: active ? `inset 0 0 0 1px ${tacticColor(t)}40` : undefined,
              }}
            >
              <div className="flex items-center gap-2">
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ background: active ? tacticColor(t) : 'rgba(255,255,255,0.2)' }}
                />
                <span
                  className="text-[11px] font-medium"
                  style={{ color: active ? tacticColor(t) : 'rgba(255,255,255,0.4)' }}
                >
                  {t}
                </span>
              </div>
              <div className="font-data text-xl text-white mt-2">{n}</div>
              <div className="text-[9px] text-white/35">
                {n === 1 ? 'sesión observada' : 'sesiones observadas'}
              </div>
              <div className="h-1 rounded bg-white/5 mt-2">
                <div
                  className="h-1 rounded"
                  style={{
                    width: `${(n / maxSessions) * 100}%`,
                    background: tacticColor(t),
                  }}
                />
              </div>
              <div className="text-[10px] text-white/45 mt-2.5 leading-relaxed">
                {TACTIC_MEANING[t]}
              </div>
            </div>
            </Reveal>
          );
        })}
      </div>

      <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
        <div className="text-[9px] uppercase tracking-wider text-white/35 mb-1">
          Etapas sobre el total capturado
        </div>
        <div className="text-[11px] text-white/45 mb-3 leading-relaxed">
          La enorme mayoría del tráfico es reconocimiento y fuerza bruta automatizada. Solo una
          fracción mínima llega a ejecutar comandos: por eso el triaje importa.
        </div>
        <div className="bar-group flex flex-col gap-2">
          {stages.map((s) => {
            const total = stages.reduce((acc, x) => acc + x.count, 0);
            const width = total ? (s.count / total) * 100 : 0;
            return (
              <div
                key={s.key}
                className="bar-item flex items-center gap-3 transition-opacity duration-200 cursor-default"
                onMouseMove={(e) =>
                  tip.show(
                    e,
                    <div className="min-w-[170px]">
                      <div className="text-[11px] text-white/90 capitalize">{s.key}</div>
                      <div className="font-data text-[15px] text-white mt-0.5">
                        {n(s.count)}
                      </div>
                      <div className="text-[10px] text-white/45 mt-0.5">eventos en esta etapa</div>
                      <div className="text-[10px] text-white/40 mt-1.5 pt-1.5 border-t border-white/8">
                        {pct(s.count, total)}% de todo lo capturado
                      </div>
                    </div>,
                  )
                }
                onMouseLeave={tip.hide}
              >
                <span className="w-32 text-[11px] text-white/60 shrink-0 capitalize">{s.key}</span>
                <div className="flex-1 h-1.5 rounded bg-white/5 overflow-hidden">
                  <div
                    className="h-1.5 rounded transition-all duration-700"
                    style={{ width: `${width}%`, background: 'var(--honey-amber)' }}
                  />
                </div>
                <span className="font-data text-[10px] text-white/45 w-24 text-right">
                  {n(s.count)} ({pct(s.count, total)}%)
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
