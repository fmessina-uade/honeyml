import { Crosshair, KeyRound, Radar } from 'lucide-react';
import type { ArchetypeData } from '../../lib/api';
import Reveal from '../Reveal';
import { n } from '../../lib/format';
import { useI18n } from '../../lib/i18n';

/**
 * Attackers grouped by how they behave, not by what they typed.
 *
 * The fingerprints section groups by byte-identical commands, which is strict and therefore blind
 * to everyone who never reached a shell. This covers every observed address and lets the data draw
 * the boundaries — which is how the section arrives at its point: almost none of them are a threat,
 * and the ones that are, are very few.
 */

/** Visual identity per archetype, keyed by the name the backend derives from the profile. */
const LOOK: Record<string, { icon: typeof Radar; color: string }> = {
  'Intrusión efectiva': { icon: Crosshair, color: 'var(--agent-coral)' },
  'Fuerza bruta': { icon: KeyRound, color: 'var(--honey-amber)' },
  Sondeo: { icon: Radar, color: 'var(--ghost-slate)' },
};

const FALLBACK = { icon: Radar, color: 'var(--ghost-slate)' };

export default function Archetypes({ data }: { data: ArchetypeData }) {
  const { t } = useI18n();
  const max = Math.max(...data.perfiles.map((p) => p.direcciones), 1);

  /** Names and copy live in the translations; the backend name is the key. */
  const copy = (nombre: string) =>
    t.archetypes.groups[nombre as keyof typeof t.archetypes.groups] ?? {
      name: nombre,
      blurb: '',
    };

  /**
   * Traits are labelled from the raw column name, not from the text the API sends.
   *
   * The API's label is Spanish, so using it left the chips untranslated with the panel in English.
   * The column name is language-neutral and already travels in the payload, which makes it the
   * right key — and avoids shipping two copies of every label from the backend.
   */
  const traitLabel = (columna: string, fallback: string) => {
    if (columna.startsWith('cmd_')) return t.archetypes.usedCmd(columna.slice(4));
    return t.archetypes.traits[columna] ?? fallback;
  };

  return (
    <section className="flex flex-col gap-4">
      <Reveal>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="text-[11px] text-white/60 leading-relaxed">{t.archetypes.lesson}</div>
        </div>
      </Reveal>

      <div className="flex flex-col gap-3">
        {data.perfiles.map((p, i) => {
          const look = LOOK[p.nombre] ?? FALLBACK;
          const Icon = look.icon;
          const c = copy(p.nombre);

          return (
            <Reveal key={p.nombre} delay={Math.min(i * 80, 240)}>
              <div className="tile rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
                <span className="tile-glow" style={{ background: look.color }} />
                <div className="relative">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2.5">
                      <Icon className="w-4 h-4" style={{ color: look.color }} />
                      <span className="text-[13px] text-white/90">{c.name}</span>
                    </div>
                    <div className="font-data text-[11px] text-white/45">
                      <span className="text-white/85">{n(p.direcciones)}</span>{' '}
                      {t.archetypes.addresses}
                      <span className="text-white/25"> · {p.porcentaje}%</span>
                    </div>
                  </div>

                  <div className="h-1 rounded bg-white/5 mt-2.5 overflow-hidden">
                    <div
                      className="h-1 rounded transition-all duration-700"
                      style={{
                        width: `${(p.direcciones / max) * 100}%`,
                        background: look.color,
                      }}
                    />
                  </div>

                  <div className="text-[11px] text-white/55 leading-relaxed mt-3">{c.blurb}</div>

                  {/* The three numbers that separate a real compromise from an attempt. */}
                  <div className="grid grid-cols-3 gap-2 mt-3">
                    {[
                      {
                        label: t.archetypes.ranCommands,
                        value: p.pct_ejecuto_comandos,
                      },
                      {
                        label: t.archetypes.downloaded,
                        value: p.pct_descargo_archivo,
                      },
                      { label: t.archetypes.gotIn, value: p.pct_logro_acceso },
                    ].map((m) => (
                      <div key={m.label} className="rounded-lg bg-white/[0.03] p-2.5">
                        <div className="font-data text-[15px] text-white/90">{m.value}%</div>
                        <div className="text-[9px] uppercase tracking-wider text-white/35 mt-0.5">
                          {m.label}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* What the grouping keyed on, in standard deviations from the population. */}
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {p.rasgos.map((r) => (
                      <span
                        key={r.columna}
                        className="font-data text-[10px] rounded-full px-2 py-0.5 ring-1 ring-white/10 bg-white/[0.03] text-white/50"
                      >
                        {traitLabel(r.columna, r.caracteristica)}
                        <span className="text-white/30">
                          {' '}
                          {r.desvios > 0 ? '+' : ''}
                          {r.desvios}σ
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </Reveal>
          );
        })}
      </div>

      <Reveal delay={300}>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.02] p-3.5">
          <div className="text-[10px] text-white/40 leading-relaxed">
            {t.archetypes.method(n(data.direcciones_analizadas), data.caracteristicas, data.grupos)}
          </div>
        </div>
      </Reveal>
    </section>
  );
}
