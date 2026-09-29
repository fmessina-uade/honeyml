import { Crosshair, KeyRound, Radar } from 'lucide-react';
import type { ArchetypeData } from '../../lib/api';
import Reveal from '../Reveal';
import AttackFunnel from '../AttackFunnel';
import { Hexagono } from '../Instrumento';
import { dec, n } from '../../lib/format';
import { useI18n } from '../../lib/i18n';

/**
 * Atacantes agrupados por cómo se comportan, no por lo que tipearon.
 *
 * La sección de huellas agrupa por comandos idénticos byte a byte, que es estricto y por eso ciego
 * a todos los que nunca llegaron a una consola. Esto cubre todas las direcciones observadas y deja
 * que los datos dibujen los límites, que es como la sección llega a su punto: casi ninguna es una
 * amenaza, y las que sí lo son, son muy pocas.
 */

/** Identidad visual por arquetipo, indexada por el nombre que el backend deriva del perfil. */
const LOOK: Record<string, { icon: typeof Radar; color: string }> = {
  'Intrusión efectiva': { icon: Crosshair, color: 'var(--agent-coral)' },
  'Fuerza bruta': { icon: KeyRound, color: 'var(--honey-amber)' },
  Sondeo: { icon: Radar, color: 'var(--ghost-slate)' },
};

const FALLBACK = { icon: Radar, color: 'var(--ghost-slate)' };

export default function Archetypes({ data }: { data: ArchetypeData }) {
  const { t } = useI18n();

  /** Los nombres y los textos viven en las traducciones; el nombre del backend es la clave. */
  const copy = (nombre: string) =>
    t.archetypes.groups[nombre as keyof typeof t.archetypes.groups] ?? {
      name: nombre,
      blurb: '',
    };

  /**
   * Los rasgos se etiquetan desde el nombre crudo de la columna y no desde el texto que manda la
   * API.
   *
   * La etiqueta de la API está en español, así que usarla dejaría los rasgos sin traducir con el
   * panel en inglés. El nombre de la columna es neutro respecto del idioma y ya viaja en la
   * respuesta, lo que lo vuelve la clave correcta y evita mandar dos copias de cada etiqueta desde
   * el backend.
   */
  const traitLabel = (columna: string, fallback: string) => {
    if (columna.startsWith('cmd_')) return t.archetypes.usedCmd(columna.slice(4));
    return t.archetypes.traits[columna] ?? fallback;
  };

  // Una sola escala de desvíos para todos los arquetipos: así se ve que uno se aparta ocho veces
  // más del promedio que otro, y no solo cuál es su rasgo más marcado.
  const maxDesvio = Math.max(
    ...data.perfiles.flatMap((p) => p.rasgos.map((r) => Math.abs(r.desvios))),
    1,
  );

  return (
    <section className="flex flex-col gap-4">
      <Reveal>
        <div className="panel p-4">
          <div className="text-[11px] text-white/60 leading-relaxed">{t.archetypes.lesson}</div>
        </div>
      </Reveal>

      {/* El embudo va antes que las tarjetas: da la forma del conjunto, y recién después conviene
          mirar quiénes componen cada escalón. */}
      <Reveal delay={40}>
        <AttackFunnel data={data} />
      </Reveal>

      <div className="grid lg:grid-cols-3 gap-3">
        {data.perfiles.map((p, i) => {
          const look = LOOK[p.nombre] ?? FALLBACK;
          const Icon = look.icon;
          const c = copy(p.nombre);

          return (
            <Reveal key={p.nombre} delay={Math.min(i * 80, 240)}>
              <div className="panel tile overflow-hidden p-4 h-full flex flex-col">
                <span className="tile-glow" style={{ background: look.color }} />
                <span
                  className="absolute inset-x-0 top-0 h-px"
                  style={{
                    background: `linear-gradient(90deg, transparent, ${look.color}, transparent)`,
                  }}
                />
                <div className="relative flex flex-col flex-1">
                  <div className="flex items-center gap-2.5">
                    <Hexagono color={look.color}>
                      <Icon className="w-3.5 h-3.5" />
                    </Hexagono>
                    <span className="titulo">{c.name}</span>
                    <span
                      className="ml-auto font-data text-[10px] rounded-full px-2 py-0.5"
                      style={{
                        color: look.color,
                        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${look.color} 45%, transparent)`,
                      }}
                    >
                      {dec(p.porcentaje, 1)}%
                    </span>
                  </div>

                  <div className="mt-3 flex items-baseline gap-2">
                    <span className="cifra">{n(p.direcciones)}</span>
                    <span className="text-[10px] text-white/40">{t.archetypes.addresses}</span>
                  </div>

                  <div className="text-[11px] text-white/55 leading-relaxed mt-2">{c.blurb}</div>

                  {/* Los tres números que separan un compromiso real de un intento */}
                  <div className="grid grid-cols-3 gap-2 mt-3">
                    {[
                      { label: t.archetypes.ranCommands, value: p.pct_ejecuto_comandos },
                      { label: t.archetypes.downloaded, value: p.pct_descargo_archivo },
                      { label: t.archetypes.gotIn, value: p.pct_logro_acceso },
                    ].map((m) => (
                      <div key={m.label} className="rounded-lg bg-white/[0.03] p-2.5">
                        <div className="cifra-chica">{dec(m.value, 1)}%</div>
                        <div className="rotulo mt-0.5">{m.label}</div>
                      </div>
                    ))}
                  </div>

                  {/* En qué se apoyó el agrupamiento: cuántos desvíos se aparta cada rasgo del
                      promedio de todas las direcciones, hacia arriba o hacia abajo. */}
                  <div className="mt-4 pt-3 border-t border-white/5">
                    <div className="rotulo mb-2">{t.archetypes.traitsTitle}</div>
                    <div className="flex flex-col gap-1.5">
                      {p.rasgos.map((r) => {
                        const largo = (Math.abs(r.desvios) / maxDesvio) * 50;
                        const positivo = r.desvios > 0;
                        return (
                          <div
                            key={r.columna}
                            className="grid grid-cols-[minmax(0,1fr)_minmax(0,40%)_66px] gap-2 items-center"
                          >
                            <span className="text-[10px] text-white/55 truncate">
                              {traitLabel(r.columna, r.caracteristica)}
                            </span>
                            <span className="relative h-2">
                              <span className="absolute inset-y-0 left-1/2 w-px bg-white/15" />
                              <span
                                className="absolute inset-y-0 rounded-sm"
                                style={{
                                  [positivo ? 'left' : 'right']: '50%',
                                  width: `max(${largo}%, 2px)`,
                                  background: positivo ? look.color : 'var(--ghost-slate)',
                                  opacity: positivo ? 0.85 : 0.55,
                                }}
                              />
                            </span>
                            <span className="font-data text-[9.5px] text-white/40 text-right whitespace-nowrap">
                              {t.archetypes.sd(`${positivo ? '+' : ''}${dec(r.desvios, 1)}`)}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </Reveal>
          );
        })}
      </div>

      <Reveal delay={300}>
        <div className="panel panel-tenue p-3.5">
          <div className="text-[10px] text-white/40 leading-relaxed">
            {t.archetypes.method(n(data.direcciones_analizadas), data.caracteristicas, data.grupos)}
          </div>
        </div>
      </Reveal>
    </section>
  );
}
