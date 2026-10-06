import type { ArchetypeData } from '../../lib/api';
import Reveal from '../Reveal';
import AttackFunnel from '../AttackFunnel';
import { Palabras } from '../Titular';
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
const LOOK: Record<string, { fondo: string; color: string }> = {
  'Intrusión efectiva': { fondo: 'intrusion', color: 'var(--agent-coral)' },
  'Fuerza bruta': { fondo: 'fuerza', color: 'var(--honey-amber)' },
  Sondeo: { fondo: 'sondeo', color: 'var(--ghost-slate)' },
};

const FALLBACK = { fondo: 'sondeo', color: 'var(--ghost-slate)' };

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

  const perfiles = [...data.perfiles].sort((a, b) => b.porcentaje - a.porcentaje);

  return (
    <section className="flex flex-col gap-14">
      {/* La presentación: un radar que asoma desde abajo, un semicírculo por grupo */}
      <div className="presentacion presentacion-radar">
        <div className="relative max-w-[1320px] mx-auto px-4 md:px-8 pt-14 sm:pt-20 flex flex-col items-center text-center">
          <span className="ceja section-in">{t.archetypes.heroBadge}</span>
          <h1 className="titular-landing mt-5">
            <Palabras texto={t.nav.arquetipos} />
          </h1>
          <p className="portada-bajada section-in">{t.lead.arquetipos}</p>
        </div>
        <Radar perfiles={perfiles} nombre={(k) => copy(k).name} />
      </div>

      <Reveal>
        <figure className="cita" style={{ borderColor: 'var(--ghost-slate)' }}>
          <span className="ceja">{t.funnel.title}</span>
          <blockquote className="mt-4">{t.archetypes.lesson}</blockquote>
        </figure>
      </Reveal>

      {/* El embudo va antes que los retratos: da la forma del conjunto, y recién después conviene
          mirar quiénes componen cada escalón. */}
      <Reveal>
        <AttackFunnel data={data} />
      </Reveal>

      {/* Un retrato por arquetipo, con su fondo propio y su lista al pie */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {data.perfiles.map((p, i) => {
          const look = LOOK[p.nombre] ?? FALLBACK;
          const c = copy(p.nombre);
          return (
            <Reveal key={p.nombre} delay={Math.min(i * 80, 240)}>
              <article
                className="retrato"
                data-arquetipo={look.fondo}
                style={{ '--tono': look.color } as React.CSSProperties}
              >
                <span className="ceja self-center">{c.name}</span>

                <div className="mt-8 text-center">
                  <div className="cifra-columna" style={{ color: look.color }}>
                    {dec(p.porcentaje, 1)}%
                  </div>
                  <div className="text-[12px] text-white/55 mt-2">
                    {n(p.direcciones)} {t.archetypes.addresses}
                  </div>
                </div>

                <p className="text-[12.5px] text-white/65 leading-relaxed mt-6">{c.blurb}</p>

                {/* Los tres números que separan un compromiso real de un intento */}
                <ul className="retrato-lista mt-auto pt-6">
                  {[
                    { label: t.archetypes.ranCommands, value: p.pct_ejecuto_comandos },
                    { label: t.archetypes.downloaded, value: p.pct_descargo_archivo },
                    { label: t.archetypes.gotIn, value: p.pct_logro_acceso },
                  ].map((m) => (
                    <li key={m.label}>
                      <span>{m.label}</span>
                      <span className="font-data">{dec(m.value, 1)}%</span>
                    </li>
                  ))}
                </ul>

                {/* En qué se apoyó el agrupamiento: cuántos desvíos se aparta cada rasgo del
                    promedio de todas las direcciones, hacia arriba o hacia abajo. */}
                <div className="mt-5 pt-4 border-t border-white/10">
                  <div className="rotulo mb-2.5">{t.archetypes.traitsTitle}</div>
                  <div className="flex flex-col gap-1.5">
                    {p.rasgos.map((r) => {
                      const largo = (Math.abs(r.desvios) / maxDesvio) * 50;
                      const positivo = r.desvios > 0;
                      return (
                        <div
                          key={r.columna}
                          className="grid grid-cols-[minmax(0,1fr)_minmax(0,40%)_66px] gap-2 items-center"
                        >
                          <span className="text-[10.5px] text-white/60 truncate">
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
              </article>
            </Reveal>
          );
        })}
      </div>

      <Reveal>
        <p className="text-[11px] text-white/40 leading-relaxed max-w-[64rem]">
          {t.archetypes.method(n(data.direcciones_analizadas), data.caracteristicas, data.grupos)}
        </p>
      </Reveal>
    </section>
  );
}

/**
 * El radar de la presentación: un semicírculo por grupo, todos con el mismo centro al pie, con el
 * área de su porcentaje. El grupo más chico, el de la intrusión efectiva, queda como un punto en el
 * centro de todo lo demás.
 */
function Radar({
  perfiles,
  nombre,
}: {
  perfiles: ArchetypeData['perfiles'];
  nombre: (k: string) => string;
}) {
  const ANCHO = 1000;
  const ALTO = 340;
  const cx = ANCHO / 2;
  const R = ALTO - 24;
  return (
    <svg
      viewBox={`0 0 ${ANCHO} ${ALTO}`}
      preserveAspectRatio="xMidYMax meet"
      className="block w-full max-w-[1100px] mx-auto mt-6"
      role="img"
      aria-label={perfiles.map((p) => `${nombre(p.nombre)} ${dec(p.porcentaje, 1)}%`).join(', ')}
    >
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <path
          key={f}
          d={`M ${cx - R * f * 1.5} ${ALTO} A ${R * f * 1.5} ${R * f * 1.5} 0 0 1 ${cx + R * f * 1.5} ${ALTO}`}
          className="radar-guia"
        />
      ))}
      {perfiles.map((p, i) => {
        const look = LOOK[p.nombre] ?? FALLBACK;
        const r = Math.max(9, R * Math.sqrt(p.porcentaje / 100));
        const lado = i % 2 === 0 ? 1 : -1;
        const ang = (lado > 0 ? 58 : 122) * (Math.PI / 180);
        const px = cx + r * Math.cos(ang);
        const py = ALTO - r * Math.sin(ang);
        return (
          <g key={p.nombre} className="radar-grupo" style={{ '--i': i } as React.CSSProperties}>
            <path
              d={`M ${cx - r} ${ALTO} A ${r} ${r} 0 0 1 ${cx + r} ${ALTO} Z`}
              style={{
                fill: look.color,
                fillOpacity: i === perfiles.length - 1 ? 0.9 : 0.06 + i * 0.07,
                stroke: look.color,
                strokeOpacity: 0.7,
              }}
            />
            <circle cx={px} cy={py} r={3} style={{ fill: look.color }} />
            <line
              x1={px}
              y1={py}
              x2={px + lado * 34}
              y2={py - 26}
              style={{ stroke: look.color, strokeOpacity: 0.6 }}
            />
            <text
              x={px + lado * 40}
              y={py - 30}
              textAnchor={lado > 0 ? 'start' : 'end'}
              className="radar-rotulo"
            >
              {nombre(p.nombre)} {dec(p.porcentaje, 1)}%
            </text>
          </g>
        );
      })}
    </svg>
  );
}
