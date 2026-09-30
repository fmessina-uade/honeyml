import { useEffect, useRef, useState } from 'react';
import rough from 'roughjs';
import { ExternalLink } from 'lucide-react';
import type { Bucket, Overview, Replay } from '../../lib/api';
import { tacticColor } from './SessionReplay';
import Reveal from '../Reveal';
import Tooltip, { useTooltip } from '../Tooltip';
import ManoAlzada from '../ManoAlzada';
import { n, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { useAncho } from '../../lib/useAncho';

// Las dos del ingreso salen de los intentos de acceso: probar claves es fuerza bruta y entrar con
// una que funciona es usar una cuenta válida. No aparecen en el replay, que empieza con la sesión
// ya abierta, así que se cuentan con los contadores de portada.
const ACCESS = ['Acceso a credenciales', 'Acceso inicial'] as const;

// Las que ejercitan los comandos de las sesiones capturadas.
const IN_SESSION = ['Descubrimiento', 'Ejecución', 'Evasión de defensas', 'Persistencia'] as const;

// Las seis que el señuelo observa, en el orden en que las recorre una intrusión. Es el mismo
// vocabulario que el motor de triaje puede asignar (TACTICAS_OBSERVABLES en annotations.py), y el
// triaje lo toma de acá para las correcciones del analista.
export const OBSERVED = [...ACCESS, ...IN_SESSION] as const;

// Técnica de MITRE que corresponde a cada táctica de acceso.
const ACCESS_TECHNIQUE: Record<(typeof ACCESS)[number], string> = {
  'Acceso a credenciales': 'T1110',
  'Acceso inicial': 'T1078',
};

// Las que un señuelo de baja interacción estructuralmente no puede ver. Mostrarlas es la gracia: el
// hueco es una propiedad del sensor y no una omisión del panel, y decirlo es lo que convierte un
// gráfico de cobertura en una explicación.
export const NOT_OBSERVED = ['Movimiento lateral', 'Impacto'] as const;

const CADENA = [...OBSERVED, ...NOT_OBSERVED];

const HEX = 'M28 3 L50 15.5 L50 40.5 L28 53 L6 40.5 L6 15.5 Z';

/** Un hexágono trazado a mano y punteado: el eslabón que el sensor no llega a ver. */
function HexagonoAMano() {
  const ref = useRef<SVGSVGElement | null>(null);
  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const rc = rough.svg(svg);
    svg.appendChild(
      rc.polygon(
        [
          [28, 3],
          [50, 15.5],
          [50, 40.5],
          [28, 53],
          [6, 40.5],
          [6, 15.5],
        ],
        {
          stroke: 'rgba(148,163,184,0.55)',
          strokeWidth: 1.3,
          roughness: 1.6,
          bowing: 1.2,
          strokeLineDash: [4, 4],
          seed: 7,
        },
      ),
    );
  }, []);
  return <svg ref={ref} viewBox="0 0 56 56" className="absolute inset-0 w-full h-full" />;
}

/**
 * Las tácticas de MITRE ATT&CK encendidas con las capturas del propio proyecto.
 *
 * Enseña el marco con evidencia que el lector acaba de ver en el replay y, más importante, es
 * explícita sobre lo que el señuelo no puede observar. Una matriz que solo muestra aciertos sugiere
 * cobertura total; una que muestra los huecos, con el motivo, enseña a leer cualquier afirmación de
 * cobertura.
 */
export default function MitreMatrix({
  replays,
  stages,
  overview,
}: {
  replays: Replay[];
  stages: Bucket[];
  overview: Overview;
}) {
  const { t } = useI18n();
  const tip = useTooltip();
  const [elegida, setElegida] = useState<string>(CADENA[0]);
  const { ref: refCadena, ancho } = useAncho<HTMLDivElement>();

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
  const accessCount: Record<(typeof ACCESS)[number], number> = {
    'Acceso a credenciales': overview.logins,
    'Acceso inicial': overview.logins_success,
  };

  const tacticName = (key: string) => t.tactics[key as keyof typeof t.tactics]?.name ?? key;
  const tacticMeaning = (key: string) => t.tactics[key as keyof typeof t.tactics]?.meaning ?? '';
  const esAcceso = (tac: string): tac is (typeof ACCESS)[number] =>
    (ACCESS as readonly string[]).includes(tac);
  const observada = (tac: string) => (OBSERVED as readonly string[]).includes(tac);

  // La cifra que va debajo de cada eslabón: eventos para las de acceso, sesiones para las demás.
  const cifra = (tac: string) =>
    esAcceso(tac) ? n(accessCount[tac]) : observada(tac) ? n(sessionsPer.get(tac) ?? 0) : null;
  const unidad = (tac: string) =>
    esAcceso(tac)
      ? tac === 'Acceso inicial'
        ? t.mitre.successes
        : t.mitre.attempts
      : (sessionsPer.get(tac) ?? 0) === 1
        ? t.mitre.session
        : t.mitre.sessions;

  // Ocho eslabones en fila cuando hay lugar, cuatro por fila en un teléfono. Se decide por el ancho
  // del contenedor, porque la anotación a mano necesita saber dónde quedaron los dos últimos.
  const porFila = ancho > 0 && ancho < 640 ? 4 : 8;
  const filas = CADENA.length / porFila;

  const color = (tac: string) => (observada(tac) ? tacticColor(tac) : 'var(--ghost-slate)');
  const techsDe = (tac: string) =>
    esAcceso(tac)
      ? [ACCESS_TECHNIQUE[tac]]
      : techList.filter(([, info]) => info.tactic === tac).map(([id]) => id);

  return (
    <section className="flex flex-col gap-4">
      <Tooltip content={tip.content} at={tip.at} />

      {/* La cadena: lo que el señuelo ve, en el orden de una intrusión, y lo que no puede ver */}
      <Reveal>
        <div className="panel p-4">
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <span className="rotulo">{t.mitre.coverageTitle}</span>
            <span className="font-data text-[10px] text-white/30">
              {t.mitre.observedOf(OBSERVED.length, CADENA.length)}
            </span>
          </div>
          <div className="text-[11px] text-white/45 mt-1.5 leading-relaxed max-w-3xl">
            {t.mitre.coverageNote}
          </div>

          <div ref={refCadena} className="relative mt-8">
            <div
              className="grid gap-y-5"
              style={{ gridTemplateColumns: `repeat(${porFila}, minmax(0, 1fr))` }}
            >
              {CADENA.map((tac, i) => {
                const visto = observada(tac);
                const activo = elegida === tac;
                const ultimoDeFila = (i + 1) % porFila === 0;
                const siguienteVisto = i + 1 < CADENA.length && observada(CADENA[i + 1]);
                return (
                  <button
                    key={tac}
                    onClick={() => setElegida(tac)}
                    aria-pressed={activo}
                    className="relative flex flex-col items-center text-center px-1 group"
                  >
                    {/* el eslabón hasta el siguiente */}
                    {!ultimoDeFila && i + 1 < CADENA.length && (
                      <span
                        className="absolute top-[27px] left-1/2 w-full h-px"
                        style={
                          siguienteVisto
                            ? {
                                background: `linear-gradient(90deg, ${color(tac)}, ${color(CADENA[i + 1])})`,
                                opacity: 0.45,
                              }
                            : {
                                backgroundImage:
                                  'repeating-linear-gradient(90deg, rgba(148,163,184,0.45) 0 4px, transparent 4px 8px)',
                              }
                        }
                      />
                    )}
                    <span
                      className={`relative w-14 h-14 transition-transform duration-300 ${
                        activo ? 'scale-110' : 'group-hover:scale-105'
                      }`}
                    >
                      {visto ? (
                        <svg
                          viewBox="0 0 56 56"
                          className="absolute inset-0 w-full h-full overflow-visible"
                        >
                          <path
                            d={HEX}
                            style={{
                              fill: `color-mix(in srgb, ${color(tac)} ${activo ? 30 : 16}%, rgb(var(--fondo)))`,
                              stroke: color(tac),
                              filter: activo
                                ? `drop-shadow(0 0 8px color-mix(in srgb, ${color(tac)} 70%, transparent))`
                                : undefined,
                            }}
                            strokeWidth={activo ? 1.8 : 1.2}
                          />
                        </svg>
                      ) : (
                        <HexagonoAMano />
                      )}
                      <span
                        className="absolute inset-0 flex items-center justify-center font-data text-[11px]"
                        style={{ color: visto ? color(tac) : 'rgba(148,163,184,0.6)' }}
                      >
                        {i + 1}
                      </span>
                    </span>
                    <span
                      className={`mt-2 text-[10.5px] leading-tight ${
                        visto ? 'text-white/80' : 'text-white/40'
                      }`}
                    >
                      {tacticName(tac)}
                    </span>
                    {visto ? (
                      <span className="font-data text-[10px] text-white/40 mt-0.5">
                        {cifra(tac)}
                      </span>
                    ) : (
                      <span className="text-[9.5px] text-white/25 mt-0.5">{t.mitre.unseen}</span>
                    )}
                  </button>
                );
              })}
            </div>
            {ancho > 0 && (
              <ManoAlzada
                trazos={[
                  {
                    tipo: 'elipse',
                    x: 100 - 100 / porFila,
                    y: 100 - 50 / filas,
                    ancho: (200 / porFila) * 1.02,
                    alto: (100 / filas) * 1.12,
                  },
                ]}
                notas={[
                  {
                    x: 99,
                    y: filas > 1 ? 50 - 7 : -16,
                    texto: t.mitre.noteUnseen,
                    alinear: 'derecha',
                    ancho: 280,
                  },
                ]}
              />
            )}
          </div>

          {/* El eslabón elegido, en detalle */}
          <div
            key={elegida}
            className="section-in mt-6 rounded-lg p-4"
            style={{
              background: `color-mix(in srgb, ${color(elegida)} 7%, transparent)`,
              boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${color(elegida)} ${observada(elegida) ? 35 : 20}%, transparent)`,
            }}
          >
            <div className="flex items-baseline justify-between gap-3 flex-wrap">
              <span className="titulo" style={{ color: color(elegida) }}>
                {tacticName(elegida)}
              </span>
              {observada(elegida) && (
                <span className="flex items-baseline gap-2">
                  <span className="cifra-chica">{cifra(elegida)}</span>
                  <span className="text-[10px] text-white/40">{unidad(elegida)}</span>
                </span>
              )}
            </div>
            <div className="text-[12px] text-white/65 mt-1.5 leading-relaxed">
              {tacticMeaning(elegida)}
            </div>

            {observada(elegida) ? (
              <>
                {elegida === 'Acceso inicial' && (
                  <div className="mt-3">
                    <div className="h-1.5 rounded bg-white/5 overflow-hidden">
                      <div
                        className="h-1.5 rounded"
                        style={{
                          width: `${overview.logins ? (overview.logins_success / overview.logins) * 100 : 0}%`,
                          background: color(elegida),
                        }}
                      />
                    </div>
                    <div className="font-data text-[10px] text-white/35 mt-1">
                      {pct(overview.logins_success, overview.logins)}% {t.mitre.ofAttempts}
                    </div>
                  </div>
                )}
                {!esAcceso(elegida) && (
                  <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3 font-data text-[10px] text-white/45">
                    <span>
                      <span className="text-white/80">{n(stepsPer.get(elegida) ?? 0)}</span>{' '}
                      {t.mitre.steps}
                    </span>
                    <span>
                      <span className="text-white/80">
                        {pct(stepsPer.get(elegida) ?? 0, totalSteps)}%
                      </span>{' '}
                      {t.mitre.ofReplayed}
                    </span>
                    <span>
                      <span className="text-white/80">{techniquesPer.get(elegida)?.size ?? 0}</span>{' '}
                      {t.mitre.techniques}
                    </span>
                  </div>
                )}
                {techsDe(elegida).length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {techsDe(elegida).map((id) => (
                      <a
                        key={id}
                        href={`https://attack.mitre.org/techniques/${id.replace('.', '/')}/`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group flex items-center gap-1.5 rounded-md px-2 py-1 transition-all hover:-translate-y-[1px]"
                        style={{
                          boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${color(elegida)} 35%, transparent)`,
                        }}
                      >
                        <span className="font-data text-[10.5px]" style={{ color: color(elegida) }}>
                          {id}
                        </span>
                        <ExternalLink className="w-2.5 h-2.5 text-white/25 group-hover:text-white/60 transition" />
                      </a>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="mt-3">
                <div className="rotulo mb-1">{t.mitre.whyNotSeen}</div>
                <div className="text-[11px] text-white/50 leading-relaxed">
                  {t.notObservedWhy[elegida as (typeof NOT_OBSERVED)[number]]}
                </div>
              </div>
            )}
          </div>
        </div>
      </Reveal>

      {/* Las técnicas: los identificadores concretos, enlazados al catálogo oficial */}
      <Reveal delay={120}>
        <div className="panel p-4">
          <div className="rotulo">{t.mitre.techTitle}</div>
          <div className="text-[11px] text-white/45 mt-1 mb-3 leading-relaxed">
            {t.mitre.techNote}
          </div>
          <div className="flex flex-wrap gap-2">
            {ACCESS.map((tac) => (
              <a
                key={ACCESS_TECHNIQUE[tac]}
                href={`https://attack.mitre.org/techniques/${ACCESS_TECHNIQUE[tac]}/`}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-center gap-2 rounded-lg px-2.5 py-1.5 transition-all hover:-translate-y-[1px]"
                style={{
                  background: `color-mix(in srgb, ${tacticColor(tac)} 6%, transparent)`,
                  boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${tacticColor(tac)} 30%, transparent)`,
                }}
              >
                <span className="font-data text-[11px]" style={{ color: tacticColor(tac) }}>
                  {ACCESS_TECHNIQUE[tac]}
                </span>
                <span className="text-[10px] text-white/35">
                  <span className="font-data">{n(accessCount[tac])}</span> {t.mitre.events}
                </span>
                <ExternalLink className="w-2.5 h-2.5 text-white/20 group-hover:text-white/50 transition" />
              </a>
            ))}
            {techList.map(([id, info]) => (
              <a
                key={id}
                href={`https://attack.mitre.org/techniques/${id.replace('.', '/')}/`}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-center gap-2 rounded-lg px-2.5 py-1.5 transition-all hover:-translate-y-[1px]"
                style={{
                  background: `color-mix(in srgb, ${tacticColor(info.tactic)} 6%, transparent)`,
                  boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${tacticColor(info.tactic)} 30%, transparent)`,
                }}
              >
                <span className="font-data text-[11px]" style={{ color: tacticColor(info.tactic) }}>
                  {id}
                </span>
                <span className="text-[10px] text-white/35">
                  <span className="font-data">{info.steps}</span> {t.mitre.steps}
                </span>
                <ExternalLink className="w-2.5 h-2.5 text-white/20 group-hover:text-white/50 transition" />
              </a>
            ))}
          </div>
        </div>
      </Reveal>

      {/* Las etapas sobre toda la captura, no solo sobre las sesiones repetidas */}
      <Reveal delay={200}>
        <div className="panel p-4">
          <div className="rotulo mb-1">{t.mitre.stagesTitle}</div>
          <div className="text-[11px] text-white/45 mb-3 leading-relaxed">{t.mitre.stagesNote}</div>
          <div className="bar-group flex flex-col gap-2">
            {stages.map((s) => {
              const width = totalStages ? (s.count / totalStages) * 100 : 0;
              return (
                <div
                  key={s.key}
                  className="bar-item grid grid-cols-[96px_minmax(0,1fr)_auto] sm:grid-cols-[128px_minmax(0,1fr)_auto] gap-3 items-center transition-opacity duration-200 cursor-default"
                  onMouseMove={(e) =>
                    tip.show(
                      e,
                      <div className="min-w-[170px]">
                        <div className="text-[11px] text-white/90 first-letter:uppercase">
                          {s.key}
                        </div>
                        <div className="cifra-chica text-white mt-0.5">{n(s.count)}</div>
                        <div className="text-[10px] text-white/45 mt-0.5">
                          {t.mitre.stageEvents}
                        </div>
                        <div className="text-[10px] text-white/40 mt-1.5 pt-1.5 border-t border-white/8">
                          {pct(s.count, totalStages)}% {t.mitre.ofEverything}
                        </div>
                      </div>,
                    )
                  }
                  onMouseLeave={tip.hide}
                >
                  <span className="text-[11px] text-white/60 truncate first-letter:uppercase">
                    {s.key}
                  </span>
                  <div className="h-1.5 rounded bg-white/5 overflow-hidden">
                    <div
                      className="h-1.5 rounded transition-all duration-700"
                      style={{ width: `${width}%`, background: 'var(--honey-amber)' }}
                    />
                  </div>
                  <span className="font-data text-[10px] text-white/45 text-right whitespace-nowrap">
                    {n(s.count)} <span className="text-white/25">{pct(s.count, totalStages)}%</span>
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
