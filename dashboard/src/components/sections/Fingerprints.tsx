import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { FingerprintData } from '../../lib/api';
import { tacticColor } from './SessionReplay';
import Reveal from '../Reveal';
import ManoAlzada from '../ManoAlzada';
import { Palabras } from '../Titular';
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

  const cifras = [
    {
      valor: n(data.total_sessions),
      rotulo: t.fingerprints.sessionsLabel,
      sub: t.fingerprints.withCommands,
    },
    {
      valor: n(data.families_found),
      rotulo: t.fingerprints.familiesLabel,
      sub: t.fingerprints.identical,
    },
    {
      valor: `${share}%`,
      rotulo: t.fingerprints.coverageLabel,
      sub: t.fingerprints.grouped(n(data.grouped_sessions)),
    },
  ];

  return (
    <section className="flex flex-col gap-14">
      {/* La presentación: la concentración en grande y el panal de cien sesiones como imagen */}
      <div className="presentacion presentacion-panal">
        <div className="relative max-w-[1320px] mx-auto px-4 md:px-8 pt-14 sm:pt-20 pb-12">
          <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-8 lg:gap-14 items-end">
            <div className="min-w-0">
              <span className="ceja section-in">{t.fingerprints.concentrationTitle}</span>
              <h1 className="titular-landing mt-5">
                <Palabras texto={t.nav.huellas} />
              </h1>
              <p className="portada-bajada section-in">{t.lead.huellas}</p>
            </div>
            {primera && (
              <div className="min-w-0 section-in">
                <div className="cifra-gigante">
                  {pct(primera.sessions, data.total_sessions, 0)}
                  <span>%</span>
                </div>
                <p className="text-[13px] text-white/60 leading-relaxed mt-3 max-w-[34rem]">
                  {t.fingerprints.concentrationNote(
                    pct(primera.sessions, data.total_sessions, 0),
                    n(maquinas),
                  )}
                </p>
              </div>
            )}
          </div>

          {/* La concentración: el dato que la lista ordenada insinúa pero no dice. */}
          {primera && (
            <div className="mt-12">
              <Panal
                celdas={celdas}
                etiquetas={etiquetas}
                notaPrimera={t.fingerprints.notePanal(celdas[0])}
              />
              <div className="flex flex-wrap gap-x-5 gap-y-2 mt-4">
                {etiquetas.map((e, k) => (
                  <span key={e} className="flex items-center gap-1.5 text-[11px] text-white/55">
                    <span className="w-2.5 h-2.5 rounded-[3px]" style={{ background: TONOS[k] }} />
                    <span className={k < 3 ? 'font-data' : ''}>{e}</span>
                    <span className="font-data text-white/30">{celdas[k]}%</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Los números del conjunto, en una regla con divisiones */}
          <div className="regla mt-12">
            {cifras.map((c) => (
              <div key={c.rotulo} className="regla-celda">
                <span className="rotulo">{c.rotulo}</span>
                <span className="cifra-fina mt-3">{c.valor}</span>
                <span className="text-[11.5px] text-white/45 mt-2 leading-snug">{c.sub}</span>
              </div>
            ))}
            {primera && (
              <>
                <div className="regla-celda">
                  <span className="rotulo">{t.fingerprints.topThree}</span>
                  <span className="cifra-fina mt-3">
                    {pct(tresPrimeras, data.total_sessions, 0)}%
                  </span>
                </div>
                <div className="regla-celda">
                  <span className="rotulo">{t.fingerprints.machinesBehind}</span>
                  <span className="cifra-fina mt-3">{n(maquinas)}</span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <Reveal>
        <figure className="cita" style={{ borderColor: 'var(--agent-coral)' }}>
          <span className="ceja">{t.fingerprints.script}</span>
          <blockquote className="mt-4">{t.fingerprints.lesson}</blockquote>
        </figure>
      </Reveal>

      {/* Cada familia, desplegable hasta su guion exacto */}
      <div className="pliego">
        <span className="ceja">{t.fingerprints.familiesLabel}</span>
        <div className="flex flex-col mt-5">
          {data.families.map((f, i) => {
            const isOpen = open === i;
            // El mismo tono que la familia tiene en el panal, que sale del orden por sesiones.
            const puesto = orden.indexOf(f);
            const tono = puesto < 3 ? TONOS[puesto] : 'var(--honey-amber)';
            return (
              <div
                key={f.label}
                className="familia"
                data-abierta={isOpen ? 'si' : undefined}
                style={{ '--tono': tono } as React.CSSProperties}
              >
                <button
                  onClick={() => setOpen(isOpen ? null : i)}
                  aria-expanded={isOpen}
                  className="w-full text-left py-4 pl-5 pr-2"
                >
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="font-data text-[11px] text-white/30 w-6 shrink-0">
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <span className="font-data text-[14px] text-white/90 truncate">
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
                    <div className="flex items-center gap-4 font-data text-[11px] text-white/45">
                      <span>
                        <span className="text-white/85">{n(f.sessions)}</span>{' '}
                        {t.fingerprints.sessions}
                      </span>
                      <span>
                        <span className="text-white/85">{n(f.sources)}</span>{' '}
                        {t.fingerprints.sources}
                      </span>
                      <span className="text-white/25 hidden sm:inline">
                        {t.footer.range(fmtDate(f.first_seen), fmtDate(f.last_seen))}
                      </span>
                      <ChevronDown
                        className={`w-4 h-4 text-white/35 transition-transform shrink-0 ${
                          isOpen ? 'rotate-180' : ''
                        }`}
                      />
                    </div>
                  </div>

                  <div className="h-1 rounded bg-white/5 mt-3 ml-9 overflow-hidden">
                    <div
                      className="h-1 rounded transition-all duration-700"
                      style={{ width: `${(f.sessions / max) * 100}%`, background: tono }}
                    />
                  </div>

                  {/* Las sesiones por dirección son la pista: muchas repeticiones desde pocas
                      máquinas. */}
                  <div className="text-[11px] text-white/35 mt-2 ml-9">
                    {t.fingerprints.perSource(
                      (f.sessions / (f.sources || 1)).toLocaleString(localeActual(), {
                        maximumFractionDigits: 1,
                      }),
                    )}
                  </div>
                </button>

                {isOpen && (
                  <div className="impreso section-in rounded-xl mx-5 mb-5 p-4">
                    <div className="rotulo mb-2">{t.fingerprints.script}</div>
                    <div className="font-data text-[11.5px] flex flex-col gap-1.5">
                      {f.commands.map((c, k) => (
                        <div key={k} className="flex gap-2">
                          <span className="text-white/25 select-none w-4 text-right shrink-0">
                            {k + 1}
                          </span>
                          <span className="text-white/75 break-all">{c}</span>
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
            );
          })}
        </div>
      </div>
    </section>
  );
}
