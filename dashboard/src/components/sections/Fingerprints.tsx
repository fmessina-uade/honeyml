import { useState } from 'react';
import { ChevronDown, Users, Repeat, Layers } from 'lucide-react';
import type { FingerprintData } from '../../lib/api';
import { tacticColor } from './SessionReplay';
import Reveal from '../Reveal';
import ManoAlzada from '../ManoAlzada';
import { Indicador } from '../Instrumento';
import { localeActual, n, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { useAncho } from '../../lib/useAncho';
import { useInView } from '../../lib/useInView';
import { useQuieto } from '../../lib/useQuieto';

// Los tonos del panal, de la familia más grande al resto.
const TONOS = [
  'var(--agent-coral)',
  'color-mix(in srgb, var(--agent-coral) 62%, transparent)',
  'color-mix(in srgb, var(--agent-coral) 38%, transparent)',
  'color-mix(in srgb, var(--honey-amber) 45%, transparent)',
  'rgb(var(--tinta) / 0.07)',
];

/**
 * Reparte cien celdas entre las partes, por el método del mayor resto: redondear cada parte por
 * separado puede dar 99 o 101, y un panal de cien celdas que no suma cien se nota.
 */
function repartir(partes: number[], total: number): number[] {
  const exactas = partes.map((p) => (total ? (p / total) * 100 : 0));
  const enteras = exactas.map(Math.floor);
  let falta = 100 - enteras.reduce((a, b) => a + b, 0);
  const porResto = exactas
    .map((v, i) => ({ i, resto: v - Math.floor(v) }))
    .sort((a, b) => b.resto - a.resto);
  for (const { i } of porResto) {
    if (falta <= 0) break;
    enteras[i]++;
    falta--;
  }
  return enteras;
}

/**
 * Cien sesiones en un panal: cada celda es una de cada cien, pintada según la familia a la que
 * pertenece. Las celdas se llenan por columnas, así cada familia queda como un bloque y la más
 * grande ocupa todo el costado izquierdo.
 */
function Panal({
  celdas,
  etiquetas,
  notaPrimera,
}: {
  celdas: number[];
  etiquetas: string[];
  notaPrimera: string;
}) {
  const { ref, ancho } = useAncho<HTMLDivElement>();
  const { ref: refVista, inView } = useInView<HTMLDivElement>(0.3);
  const quieto = useQuieto();
  // Diez filas en un teléfono, cinco en una pantalla mediana y cuatro cuando sobra ancho: así el
  // panal ocupa el panel sin que las celdas pasen de un tamaño legible.
  const filas = ancho > 0 && ancho < 520 ? 10 : ancho < 900 ? 5 : 4;
  const columnas = 100 / filas;
  // Hexágonos con la punta arriba: el ancho es raíz de tres por el radio y las filas se solapan un
  // cuarto de su alto. Las filas impares se corren medio hexágono.
  const r = ancho > 0 ? Math.min(ancho / ((columnas + 0.5) * Math.sqrt(3)), 24) : 0;
  const w = Math.sqrt(3) * r;
  const alto = r > 0 ? filas * 1.5 * r + 0.5 * r : 0;
  const hueco = 0.88;

  const categoria: number[] = [];
  celdas.forEach((c, k) => {
    for (let i = 0; i < c; i++) categoria.push(k);
  });

  const hexagono = (cx: number, cy: number) =>
    Array.from({ length: 6 }, (_, i) => {
      const a = (Math.PI / 3) * i - Math.PI / 2;
      return `${cx + r * hueco * Math.cos(a)},${cy + r * hueco * Math.sin(a)}`;
    }).join(' ');

  const centro = (i: number) => {
    const col = Math.floor(i / filas);
    const fila = i % filas;
    return { cx: w / 2 + col * w + (fila % 2 ? w / 2 : 0), cy: r + fila * 1.5 * r };
  };

  const columnasPrimera = Math.ceil((celdas[0] ?? 0) / filas);
  const anchoPrimera = columnasPrimera * w + w / 2;
  const anchoTotal = columnas * w + w / 2;
  // El lienzo de la anotación suma los 36 píxeles de aire de arriba, donde va la nota.
  const altoLienzo = alto + 36;

  return (
    <div ref={ref} className="w-full">
      <div ref={refVista} className="relative pt-9" style={{ width: anchoTotal || '100%' }}>
        {r > 0 && (
          <svg width={anchoTotal} height={alto} className="block overflow-visible">
            {categoria.map((k, i) => {
              const { cx, cy } = centro(i);
              return (
                <polygon
                  key={i}
                  points={hexagono(cx, cy)}
                  style={{
                    fill: TONOS[k],
                    opacity: inView || quieto ? 1 : 0,
                    transition: quieto ? undefined : `opacity 420ms ease ${i * 9}ms`,
                  }}
                >
                  <title>{etiquetas[k]}</title>
                </polygon>
              );
            })}
          </svg>
        )}
        {r > 0 && celdas[0] > 0 && (
          <ManoAlzada
            trazos={[
              {
                tipo: 'elipse',
                x: (anchoPrimera / 2 / anchoTotal) * 100,
                y: ((36 + alto / 2) / altoLienzo) * 100,
                ancho: ((anchoPrimera + 22) / anchoTotal) * 100,
                alto: ((alto + 14) / altoLienzo) * 100,
              },
            ]}
            notas={[{ x: 1, y: (2 / altoLienzo) * 100, texto: notaPrimera, ancho: 340 }]}
          />
        )}
      </div>
    </div>
  );
}

/**
 * Sesiones agrupadas por secuencia de comandos idéntica byte a byte.
 *
 * Es la sección que convierte "capturamos un montón de ataques" en "capturamos unos pocos
 * programas, muchas veces". Una familia es un conjunto de sesiones cuyos comandos coinciden exacto,
 * una definición estricta que no puede agrupar cosas por casualidad, así que toda familia que se
 * muestra es real.
 */
export default function Fingerprints({ data }: { data: FingerprintData }) {
  const { t } = useI18n();
  const [open, setOpen] = useState<number | null>(0);

  const share = pct(data.grouped_sessions, data.total_sessions, 0);
  const max = Math.max(...data.families.map((f) => f.sessions), 1);

  /**
   * Cuánto del total se explica con unas pocas familias.
   *
   * La lista ordenada ya insinúa que arriba está todo el peso, pero obliga a sumar de a ojo. Esto
   * lo dice: la primera familia sola, y las tres primeras juntas, contra el total.
   */
  const orden = [...data.families].sort((a, b) => b.sessions - a.sessions);
  const primera = orden[0];
  const tresPrimeras = orden.slice(0, 3).reduce((s, f) => s + f.sessions, 0);
  // Direcciones distintas de la familia más grande: es lo que separa "muchos atacantes" de
  // "un programa corriendo en muchas máquinas".
  const maquinas = primera?.sources ?? 0;

  const partes = [
    ...orden.slice(0, 3).map((f) => f.sessions),
    Math.max(data.grouped_sessions - tresPrimeras, 0),
    Math.max(data.total_sessions - data.grouped_sessions, 0),
  ];
  const celdas = repartir(partes, data.total_sessions);
  const etiquetas = [
    ...orden.slice(0, 3).map((f) => f.label),
    t.fingerprints.otherFamilies,
    t.fingerprints.ungrouped,
  ];

  const tacticName = (key: string) => t.tactics[key as keyof typeof t.tactics]?.name ?? key;
  const fmtDate = (iso?: string) =>
    iso
      ? new Date(iso).toLocaleDateString(localeActual(), {
          day: 'numeric',
          month: 'short',
        })
      : '—';

  return (
    <section className="flex flex-col gap-4">
      {/* Lo primero: casi todo el tráfico es un puñado de guiones */}
      <div className="grid sm:grid-cols-3 gap-3">
        <Reveal>
          <Indicador
            icono={Repeat}
            rotulo={t.fingerprints.sessionsLabel}
            valor={n(data.total_sessions)}
            sub={t.fingerprints.withCommands}
            color="var(--honey-amber)"
          />
        </Reveal>
        <Reveal delay={70}>
          <Indicador
            icono={Users}
            rotulo={t.fingerprints.familiesLabel}
            valor={n(data.families_found)}
            sub={t.fingerprints.identical}
            color="var(--agent-coral)"
          />
        </Reveal>
        <Reveal delay={140}>
          <Indicador
            icono={Layers}
            rotulo={t.fingerprints.coverageLabel}
            valor={`${share}%`}
            sub={t.fingerprints.grouped(n(data.grouped_sessions))}
            color="var(--neural-teal)"
          />
        </Reveal>
      </div>

      {/* La concentración: el dato que la lista ordenada insinúa pero no dice. */}
      {primera && (
        <Reveal delay={60}>
          <div className="panel p-4">
            <div className="rotulo mb-2">{t.fingerprints.concentrationTitle}</div>

            <Panal
              celdas={celdas}
              etiquetas={etiquetas}
              notaPrimera={t.fingerprints.notePanal(celdas[0])}
            />

            <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3">
              {etiquetas.map((e, k) => (
                <span key={e} className="flex items-center gap-1.5 text-[10px] text-white/50">
                  <span className="w-2.5 h-2.5 rounded-[3px]" style={{ background: TONOS[k] }} />
                  <span className={k < 3 ? 'font-data' : ''}>{e}</span>
                  <span className="font-data text-white/30">{celdas[k]}%</span>
                </span>
              ))}
            </div>

            <div className="grid grid-cols-3 gap-2 mt-4">
              {[
                {
                  valor: `${pct(primera.sessions, data.total_sessions, 0)}%`,
                  rotulo: t.fingerprints.topOne,
                },
                {
                  valor: `${pct(tresPrimeras, data.total_sessions, 0)}%`,
                  rotulo: t.fingerprints.topThree,
                },
                { valor: n(maquinas), rotulo: t.fingerprints.machinesBehind },
              ].map((m) => (
                <div key={m.rotulo} className="rounded-lg bg-white/[0.03] p-2.5">
                  <div className="cifra-chica">{m.valor}</div>
                  <div className="rotulo mt-0.5">{m.rotulo}</div>
                </div>
              ))}
            </div>

            <div className="text-[11px] text-white/55 leading-relaxed mt-3">
              {t.fingerprints.concentrationNote(
                pct(primera.sessions, data.total_sessions, 0),
                n(maquinas),
              )}
            </div>
          </div>
        </Reveal>
      )}

      <Reveal delay={100}>
        <div className="panel p-4">
          <div className="text-[11px] text-white/60 leading-relaxed">{t.fingerprints.lesson}</div>
        </div>
      </Reveal>

      {/* Cada familia, desplegable hasta su guion exacto */}
      <div className="flex flex-col gap-2">
        {data.families.map((f, i) => {
          const isOpen = open === i;
          // El mismo tono que la familia tiene en el panal, que sale del orden por sesiones.
          const puesto = orden.indexOf(f);
          return (
            <Reveal key={f.label} delay={Math.min(i * 50, 300)}>
              <div className="panel overflow-hidden">
                <button
                  onClick={() => setOpen(isOpen ? null : i)}
                  aria-expanded={isOpen}
                  className="w-full text-left p-4 hover:bg-white/[0.02] transition"
                >
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <ChevronDown
                        className={`w-3.5 h-3.5 text-white/30 transition-transform shrink-0 ${
                          isOpen ? 'rotate-180' : ''
                        }`}
                      />
                      <span className="font-data text-[12px] text-white/85 truncate">
                        {f.label}
                      </span>
                      <div className="flex items-center gap-1 shrink-0">
                        {f.tactics.map((tac) => (
                          <span
                            key={tac}
                            title={tacticName(tac)}
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ background: tacticColor(tac) }}
                          />
                        ))}
                      </div>
                    </div>
                    <div className="flex items-center gap-4 font-data text-[10px] text-white/45">
                      <span>
                        <span className="text-white/80">{n(f.sessions)}</span>{' '}
                        {t.fingerprints.sessions}
                      </span>
                      <span>
                        <span className="text-white/80">{n(f.sources)}</span>{' '}
                        {t.fingerprints.sources}
                      </span>
                      <span className="text-white/25 hidden sm:inline">
                        {t.footer.range(fmtDate(f.first_seen), fmtDate(f.last_seen))}
                      </span>
                    </div>
                  </div>

                  <div className="h-1 rounded bg-white/5 mt-2.5 overflow-hidden">
                    <div
                      className="h-1 rounded transition-all duration-700"
                      style={{
                        width: `${(f.sessions / max) * 100}%`,
                        background: puesto < 3 ? TONOS[puesto] : 'var(--honey-amber)',
                      }}
                    />
                  </div>

                  {/* Las sesiones por dirección son la pista: muchas repeticiones desde pocas
                      máquinas. */}
                  <div className="text-[10px] text-white/35 mt-1.5">
                    {t.fingerprints.perSource(
                      (f.sessions / (f.sources || 1)).toLocaleString(localeActual(), {
                        maximumFractionDigits: 1,
                      }),
                    )}
                  </div>
                </button>

                {isOpen && (
                  <div className="impreso section-in border-t border-white/5 p-4">
                    <div className="rotulo mb-2">{t.fingerprints.script}</div>
                    <div className="font-data text-[11px] flex flex-col gap-1.5">
                      {f.commands.map((c, k) => (
                        <div key={k} className="flex gap-2">
                          <span className="text-white/25 select-none w-4 text-right shrink-0">
                            {k + 1}
                          </span>
                          <span className="text-white/70 break-all">{c}</span>
                        </div>
                      ))}
                      {f.truncated && (
                        <div className="text-white/25 mt-1">
                          {t.fingerprints.truncated(f.total_commands)}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </Reveal>
          );
        })}
      </div>
    </section>
  );
}
