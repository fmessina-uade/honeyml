import { ExternalLink } from 'lucide-react';
import type { Bucket, Replay } from '../../lib/api';
import { tacticColor } from './SessionReplay';
import Reveal from '../Reveal';
import Tooltip, { useTooltip } from '../Tooltip';
import { n, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';

// Las cuatro tácticas que las capturas ejercitan de verdad, en el orden en que las recorre una intrusión.
const OBSERVED = ['Descubrimiento', 'Ejecución', 'Evasión de defensas', 'Persistencia'] as const;

// Las que un señuelo de baja interacción estructuralmente no puede ver. Mostrarlas en gris es la
// gracia: el hueco es una propiedad del sensor y no una omisión del panel, y decirlo es lo que
// convierte un gráfico de cobertura en una explicación.
const NOT_OBSERVED = ['Acceso a credenciales', 'Movimiento lateral', 'Impacto'] as const;

/**
 * Las tácticas de MITRE ATT&CK encendidas con las capturas del propio proyecto.
 *
 * Enseña el marco con evidencia que el lector acaba de ver en el replay y, más importante, es
 * explícita sobre lo que el señuelo no puede observar. Una matriz que solo muestra aciertos sugiere
 * cobertura total; una que muestra los huecos, con el motivo, enseña a leer cualquier afirmación de
 * cobertura.
 */
export default function MitreMatrix({ replays, stages }: { replays: Replay[]; stages: Bucket[] }) {
  const { t } = useI18n();
  const tip = useTooltip();

  // cuántas sesiones capturadas tocaron cada táctica, y cuántos pasos del replay
  const sessionsPer = new Map<string, number>();
  const stepsPer = new Map<string, number>();
  const techniquesPer = new Map<string, Set<string>>();
  for (const r of replays) {
    for (const tac of r.tactics) sessionsPer.set(tac, (sessionsPer.get(tac) ?? 0) + 1);
    for (const s of r.steps) {
      stepsPer.set(s.tactic, (stepsPer.get(s.tactic) ?? 0) + 1);
      if (s.technique) {
        const set = techniquesPer.get(s.tactic) ?? new Set<string>();
        set.add(s.technique);
        techniquesPer.set(s.tactic, set);
      }
    }
  }

  const totalSteps = [...stepsPer.values()].reduce((a, b) => a + b, 0);
  const maxSteps = Math.max(...stepsPer.values(), 1);
  const totalStages = stages.reduce((a, b) => a + b.count, 0);

  // cada técnica distinta observada, con la táctica a la que pertenece y cuántas veces apareció
  const techniques = new Map<string, { tactic: string; steps: number }>();
  for (const r of replays) {
    for (const s of r.steps) {
      if (!s.technique) continue;
      const prev = techniques.get(s.technique);
      techniques.set(s.technique, {
        tactic: s.tactic,
        steps: (prev?.steps ?? 0) + 1,
      });
    }
  }
  const techList = [...techniques.entries()].sort((a, b) => b[1].steps - a[1].steps);

  const tacticName = (key: string) =>
    t.tactics[key as keyof typeof t.tactics]?.name ?? key;
  const tacticMeaning = (key: string) =>
    t.tactics[key as keyof typeof t.tactics]?.meaning ?? '';

  return (
    <section className="flex flex-col gap-4">
      <Tooltip content={tip.content} at={tip.at} />

      {/* Coverage: what the decoy sees and what it structurally cannot */}
      <Reveal>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <span className="text-[9px] uppercase tracking-wider text-white/35">
              {t.mitre.coverageTitle}
            </span>
            <span className="font-data text-[10px] text-white/30">
              {OBSERVED.length}/{OBSERVED.length + NOT_OBSERVED.length} {t.mitre.observed}
            </span>
          </div>
          <div className="text-[11px] text-white/45 mt-1.5 leading-relaxed">
            {t.mitre.coverageNote}
          </div>

          {/* a single band, observed segments coloured and the rest hatched */}
          <div className="flex gap-1 mt-3">
            {OBSERVED.map((tac) => (
              <div
                key={tac}
                className="flex-1 h-1.5 rounded-full"
                style={{ background: tacticColor(tac) }}
              />
            ))}
            {NOT_OBSERVED.map((tac) => (
              <div
                key={tac}
                className="flex-1 h-1.5 rounded-full bg-white/8 border border-dashed border-white/15"
              />
            ))}
          </div>
        </div>
      </Reveal>

      {/* Observed tactics, ranked by how much of the replay material they account for */}
      <div className="bar-group grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {OBSERVED.map((tac, idx) => {
          const sessions = sessionsPer.get(tac) ?? 0;
          const steps = stepsPer.get(tac) ?? 0;
          const techs = techniquesPer.get(tac)?.size ?? 0;
          return (
            <Reveal key={tac} delay={idx * 90}>
              <div
                className="bar-item tile rounded-xl p-4 h-full transition-opacity duration-200 cursor-default"
                style={{
                  background: `${tacticColor(tac)}12`,
                  boxShadow: `inset 0 0 0 1px ${tacticColor(tac)}40`,
                }}
                onMouseMove={(e) =>
                  tip.show(
                    e,
                    <div className="min-w-[180px]">
                      <div className="text-[11px]" style={{ color: tacticColor(tac) }}>
                        {tacticName(tac)}
                      </div>
                      <div className="flex flex-col gap-1 mt-1.5 text-[10px] text-white/55">
                        <span className="flex justify-between gap-4">
                          {t.mitre.sessions}
                          <span className="font-data text-white/85">{sessions}</span>
                        </span>
                        <span className="flex justify-between gap-4">
                          {t.mitre.steps}
                          <span className="font-data text-white/85">{n(steps)}</span>
                        </span>
                        <span className="flex justify-between gap-4">
                          {t.mitre.techniques}
                          <span className="font-data text-white/85">{techs}</span>
                        </span>
                      </div>
                      <div className="text-[10px] text-white/35 mt-1.5 pt-1.5 border-t border-white/8">
                        {pct(steps, totalSteps)}% {t.mitre.ofEverything}
                      </div>
                    </div>,
                  )
                }
                onMouseLeave={tip.hide}
              >
                <span className="tile-glow" style={{ background: tacticColor(tac) }} />
                <div className="relative">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ background: tacticColor(tac) }}
                    />
                    <span
                      className="text-[11px] font-medium"
                      style={{ color: tacticColor(tac) }}
                    >
                      {tacticName(tac)}
                    </span>
                  </div>

                  <div className="flex items-baseline gap-2 mt-2">
                    <span className="font-data text-xl text-white">{sessions}</span>
                    <span className="text-[9px] text-white/35">
                      {sessions === 1 ? t.mitre.session : t.mitre.sessions}
                    </span>
                  </div>

                  {/* share of the replay material, which is what "how much of the attack is
                      this tactic" actually means */}
                  <div className="h-1 rounded bg-white/5 mt-2 overflow-hidden">
                    <div
                      className="h-1 rounded transition-all duration-700"
                      style={{
                        width: `${(steps / maxSteps) * 100}%`,
                        background: tacticColor(tac),
                        transitionDelay: `${idx * 80}ms`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-[9px] text-white/30 mt-1">
                    <span>
                      {n(steps)} {t.mitre.steps}
                    </span>
                    <span className="font-data">
                      {techs} {t.mitre.techniques}
                    </span>
                  </div>

                  <div className="text-[10px] text-white/45 mt-2.5 leading-relaxed">
                    {tacticMeaning(tac)}
                  </div>
                </div>
              </div>
            </Reveal>
          );
        })}
      </div>

      {/* The honest half: what this sensor cannot see, and why */}
      <Reveal delay={120}>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.02] p-4">
          <div className="text-[9px] uppercase tracking-wider text-white/30 mb-3">
            {t.mitre.notObserved}
          </div>
          <div className="grid sm:grid-cols-3 gap-3">
            {NOT_OBSERVED.map((tac) => (
              <div
                key={tac}
                className="rounded-lg border border-dashed border-white/10 p-3 bg-white/[0.01]"
              >
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-white/15" />
                  <span className="text-[11px] text-white/45">{tacticName(tac)}</span>
                </div>
                <div className="text-[10px] text-white/35 mt-1.5 leading-relaxed">
                  {tacticMeaning(tac)}
                </div>
                <div className="text-[8px] uppercase tracking-wider text-white/20 mt-2.5 mb-1">
                  {t.mitre.whyNotSeen}
                </div>
                <div className="text-[10px] text-white/40 leading-relaxed">
                  {t.notObservedWhy[tac]}
                </div>
              </div>
            ))}
          </div>
        </div>
      </Reveal>

      {/* Techniques: the concrete identifiers, linked to the official catalogue */}
      <Reveal delay={160}>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="text-[9px] uppercase tracking-wider text-white/35">
            {t.mitre.techTitle}
          </div>
          <div className="text-[11px] text-white/45 mt-1 mb-3 leading-relaxed">
            {t.mitre.techNote}
          </div>
          <div className="flex flex-wrap gap-2">
            {techList.map(([id, info]) => (
              <a
                key={id}
                href={`https://attack.mitre.org/techniques/${id.replace('.', '/')}/`}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-center gap-2 rounded-lg px-2.5 py-1.5 ring-1 transition-all hover:-translate-y-[1px]"
                style={{
                  background: `${tacticColor(info.tactic)}10`,
                  borderColor: 'transparent',
                  boxShadow: `inset 0 0 0 1px ${tacticColor(info.tactic)}30`,
                }}
              >
                <span
                  className="font-data text-[11px]"
                  style={{ color: tacticColor(info.tactic) }}
                >
                  {id}
                </span>
                <span className="text-[10px] text-white/35">
                  {info.steps} {t.mitre.steps}
                </span>
                <ExternalLink className="w-2.5 h-2.5 text-white/20 group-hover:text-white/50 transition" />
              </a>
            ))}
          </div>
        </div>
      </Reveal>

      {/* Stages over the whole capture, not just the replayed sessions */}
      <Reveal delay={200}>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="text-[9px] uppercase tracking-wider text-white/35 mb-1">
            {t.mitre.stagesTitle}
          </div>
          <div className="text-[11px] text-white/45 mb-3 leading-relaxed">
            {t.mitre.stagesNote}
          </div>
          <div className="bar-group flex flex-col gap-2">
            {stages.map((s) => {
              const width = totalStages ? (s.count / totalStages) * 100 : 0;
              return (
                <div
                  key={s.key}
                  className="bar-item flex items-center gap-3 transition-opacity duration-200 cursor-default"
                  onMouseMove={(e) =>
                    tip.show(
                      e,
                      <div className="min-w-[170px]">
                        <div className="text-[11px] text-white/90 first-letter:uppercase">
                          {s.key}
                        </div>
                        <div className="font-data text-[15px] text-white mt-0.5">{n(s.count)}</div>
                        <div className="text-[10px] text-white/45 mt-0.5">{t.mitre.stageEvents}</div>
                        <div className="text-[10px] text-white/40 mt-1.5 pt-1.5 border-t border-white/8">
                          {pct(s.count, totalStages)}% {t.mitre.ofEverything}
                        </div>
                      </div>,
                    )
                  }
                  onMouseLeave={tip.hide}
                >
                  <span className="w-32 text-[11px] text-white/60 shrink-0 first-letter:uppercase">
                    {s.key}
                  </span>
                  <div className="flex-1 h-1.5 rounded bg-white/5 overflow-hidden">
                    <div
                      className="h-1.5 rounded transition-all duration-700"
                      style={{ width: `${width}%`, background: 'var(--honey-amber)' }}
                    />
                  </div>
                  <span className="font-data text-[10px] text-white/45 w-24 text-right">
                    {n(s.count)} ({pct(s.count, totalStages)}%)
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </Reveal>
    </section>
  );
}
