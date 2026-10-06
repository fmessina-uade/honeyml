import { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Fingerprint,
  KeyRound,
  TerminalSquare,
} from 'lucide-react';
import type { HourPoint, Overview, TimelinePoint, WeeklyRhythm } from '../../lib/api';
import CountUp from '../CountUp';
import Reveal from '../Reveal';
import Tooltip, { useTooltip } from '../Tooltip';
import ManoAlzada, { type Nota, type Trazo } from '../ManoAlzada';
import { n, pct, dec, localeActual } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import TimelineControls, {
  ATAJOS,
  type Atajo,
  type Interval,
  type Sensor,
} from '../TimelineControls';
import WeekHeatmap from '../WeekHeatmap';
import { api } from '../../lib/api';

const SENSOR_COLOR: Record<string, string> = {
  cowrie: 'var(--honey-amber)',
  dionaea: 'var(--neural-teal)',
};

/**
 * Fecha larga para el tooltip: "lunes, 3 de junio". Se lee mejor que una cadena ISO.
 *
 * La vista horaria etiqueta sus puntos como "AAAA-MM-DD HH", así que hay que separar la hora antes
 * de parsear la fecha. Partir la etiqueta entera por guiones deja el día pegado a la hora, que
 * parsea como NaN y hace que los tooltips horarios digan "Invalid Date".
 */
function longDate(etiqueta: string): string {
  const [fecha, hora] = etiqueta.split(' ');
  const [y, m, d] = fecha.split('-').map(Number);
  if (!y || !m || !d) return etiqueta;

  const texto = new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(localeActual(), {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  });
  return hora ? `${texto}, ${hora.padStart(2, '0')}:00 UTC` : texto;
}

/** Fecha corta para las anotaciones a mano: "3 de junio". */
function fechaCorta(etiqueta: string): string {
  const [y, m, d] = etiqueta.split(' ')[0].split('-').map(Number);
  if (!y || !m || !d) return etiqueta;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(localeActual(), {
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  });
}

// Qué parte de la altura ocupa la barra más alta. El resto queda libre para las anotaciones.
const ALTURA_BARRAS = 78;
// En el gráfico por hora las barras son casi iguales, así que la nota necesita más lugar arriba.
const ALTURA_HORAS = 58;

/**
 * La apertura: la escala cruda. Una máquina que nadie anunció, bajo ataque constante.
 *
 * Las barras diarias van separadas por sensor en vez de sumadas. Eso es lo que hace legible la
 * caída de Dionaea, en lugar de que parezca una baja en los ataques.
 */
export default function Pulse({
  overview,
  timeline: timelineBase,
  hourly,
  weekly,
}: {
  overview: Overview;
  timeline: TimelinePoint[];
  hourly: HourPoint[];
  weekly?: WeeklyRhythm;
}) {
  const { t } = useI18n();
  const tip = useTooltip();

  // La serie del snapshot es la vista por defecto. En cuanto se toca un filtro se pide una serie
  // nueva a la API y se muestra esa; volver a "por día" y "ambos" recupera la original sin pedir
  // nada, que es la combinación que el snapshot ya trae.
  const minimo = (overview.first_event ?? '').slice(0, 10);
  const maximo = (overview.last_event ?? '').slice(0, 10);

  const [interval, setInterval] = useState<Interval>('day');
  const [sensor, setSensor] = useState<Sensor>('todos');
  const [desde, setDesde] = useState(minimo);
  const [hasta, setHasta] = useState(maximo);
  const [serie, setSerie] = useState<TimelinePoint[] | null>(null);
  const [cargando, setCargando] = useState(false);
  /** Por qué no se pudo aplicar el filtro pedido. Ver el efecto que lo asigna. */
  const [problema, setProblema] = useState<string | null>(null);

  const completo = desde === minimo && hasta === maximo;

  // Un filtro que no se pudo aplicar no cuenta como filtro. Se distingue de `completo` (que es un
  // hecho sobre las fechas y gobierna qué se pide) porque este gobierna qué se dice: sin la
  // distinción, el encabezado anunciaría el rango elegido sobre un gráfico que muestra el período
  // entero.
  const filtroAplicado = !completo && problema === null;

  // Cambiar el intervalo ajusta el rango cuando hace falta: por hora sobre los tres meses completos
  // son más de dos mil barras en novecientos píxeles, y solo los huecos entre ellas ya ocupan más
  // que el ancho disponible, así que el gráfico saldría vacío. Volver a día o semana recupera todo.
  const cambiarIntervalo = (i: Interval) => {
    setInterval(i);
    if (i === 'hour' && completo) {
      const fin = new Date(`${maximo}T00:00:00`);
      const ini = new Date(fin);
      ini.setDate(ini.getDate() - 6);
      const iso = (d: Date) => d.toISOString().slice(0, 10);
      setDesde(iso(ini) < minimo ? minimo : iso(ini));
    } else if (i !== 'hour' && !completo && desde !== minimo) {
      setDesde(minimo);
    }
  };

  /** Corre `dias` hacia atrás desde el último día capturado, sin pasarse del primero. */
  const desplazar = (dias: number): string => {
    const d = new Date(`${maximo}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() - dias);
    const iso = d.toISOString().slice(0, 10);
    return iso < minimo ? minimo : iso;
  };

  const aplicarAtajo = (a: Atajo) => {
    const { dias, interval: i } = ATAJOS[a];
    setInterval(i);
    if (dias === null) {
      setDesde(minimo);
      setHasta(maximo);
      return;
    }
    // El atajo del día anterior es un solo día y no un rango: los dos extremos se mueven juntos.
    const fin = a === 'ayer' ? desplazar(1) : maximo;
    setDesde(a === 'ayer' ? fin : desplazar(dias));
    setHasta(fin);
  };

  /** Qué atajo describe el rango actual, para poder marcarlo sin guardar estado duplicado. */
  const atajoActivo: Atajo | null =
    (Object.keys(ATAJOS) as Atajo[]).find((a) => {
      const { dias, interval: i } = ATAJOS[a];
      if (i !== interval) return false;
      if (dias === null) return desde === minimo && hasta === maximo;
      const fin = a === 'ayer' ? desplazar(1) : maximo;
      return hasta === fin && desde === (a === 'ayer' ? fin : desplazar(dias));
    }) ?? null;

  useEffect(() => {
    if (interval === 'day' && sensor === 'todos' && completo) {
      setSerie(null);
      return;
    }
    let vigente = true;
    setCargando(true);
    api
      .timeline(interval, sensor, desde, hasta)
      .then((d) => {
        // Una respuesta que llega tarde, después de que el usuario cambió de filtro otra vez, no
        // debe pisar a la que corresponde al filtro actual.
        if (!vigente) return;
        setSerie(d);
        setProblema(null);
      })
      .catch((e: Error) => {
        if (!vigente) return;
        // Sin avisar, el gráfico volvería en silencio al período completo con los controles
        // marcando el rango elegido. El motivo lo explica la API.
        setSerie(null);
        setProblema(e.message);
      })
      .finally(() => vigente && setCargando(false));
    return () => {
      vigente = false;
    };
  }, [interval, sensor, desde, hasta, completo]);

  const timeline = serie ?? timelineBase;

  // Las tarjetas describen la captura completa; el gráfico, lo seleccionado. Los números grandes
  // vienen del resumen y no se filtran, así que lo derivado también sale de la serie completa: de
  // la filtrada, elegir una semana mostraría el total de la captura dividido por los días de otro
  // rango.
  const days = timelineBase.filter((d) => d.count > 0).length;
  const perDay = days ? Math.round(overview.events / days) : 0;
  const peak = timelineBase.reduce((a, b) => (b.count > a.count ? b : a), timelineBase[0]);

  const tiles = [
    {
      icon: Activity,
      label: t.pulse.events,
      value: overview.events,
      sub: t.pulse.perDay(n(perDay)),
      glow: 'var(--honey-amber)',
      detail: t.pulse.peak(n(peak?.count ?? 0), peak ? longDate(peak.date) : '—'),
    },
    {
      icon: Fingerprint,
      label: t.pulse.addresses,
      value: overview.unique_ips,
      sub: t.pulse.inDays(days),
      glow: 'var(--neural-teal)',
      detail: t.pulse.oneEvery(Math.round((days * 24 * 60) / (overview.unique_ips || 1))),
    },
    {
      icon: KeyRound,
      label: t.pulse.logins,
      value: overview.logins,
      sub: t.pulse.gotIn(n(overview.logins_success)),
      glow: 'var(--agent-coral)',
      detail: t.pulse.hitRate(pct(overview.logins_success, overview.logins)),
    },
    {
      icon: TerminalSquare,
      label: t.pulse.commands,
      value: overview.commands,
      sub: t.pulse.insideDecoy,
      glow: 'var(--honey-amber)',
      detail: t.pulse.perSession(dec(overview.commands / (overview.logins_success || 1))),
    },
  ];

  const max = Math.max(...timeline.map((d) => d.count), 1);

  // La anotación a mano del gráfico diario: encierra el pico de lo que se está viendo y dice cuándo
  // fue. Sale de la serie visible, así sigue al filtro.
  const iPico = timeline.reduce((mejor, d, i) => (d.count > timeline[mejor].count ? i : mejor), 0);
  const pico = timeline[iPico];
  const xPico = timeline.length ? ((iPico + 0.5) / timeline.length) * 100 : 50;
  const aLaIzquierda = xPico > 55;
  const yPico = 100 - ALTURA_BARRAS;
  const trazosDelPico: Trazo[] = [
    {
      tipo: 'elipse',
      x: xPico,
      y: yPico + 7,
      ancho: Math.max((100 / Math.max(timeline.length, 1)) * 4, 4.5),
      alto: 28,
    },
    {
      tipo: 'flecha',
      desde: [aLaIzquierda ? xPico - 12 : xPico + 12, 9],
      hasta: [aLaIzquierda ? xPico - 3 : xPico + 3, yPico + 1],
      curva: aLaIzquierda ? -0.35 : 0.35,
    },
  ];
  const notasDelPico: Nota[] = pico
    ? [
        {
          x: aLaIzquierda ? xPico - 13 : xPico + 13,
          y: -2,
          texto: t.pulse.notePeak(n(pico.count), fechaCorta(pico.date)),
          alinear: aLaIzquierda ? 'derecha' : 'izquierda',
          ancho: 200,
        },
      ]
    : [];
  const maxHour = Math.max(...hourly.map((h) => h.count), 1);
  const minHour = hourly.length ? Math.min(...hourly.map((h) => h.count)) : 0;
  // pico contra valle: un ritmo humano queda bastante por encima de 3x, la automatización cerca de 1
  const ratio = minHour > 0 ? maxHour / minHour : 0;
  const promedioHora = hourly.length ? hourly.reduce((a, h) => a + h.count, 0) / hourly.length : 0;

  const sensors = Object.keys(overview.by_sensor);

  // Cuando el filtro no se pudo aplicar, toda la sección vuelve a hablar del período completo. Que
  // un bloque honre la selección y el de al lado no es peor que no filtrar: son dos paneles
  // contándose cosas distintas sin decir cuál manda.
  const desdeVisto = filtroAplicado ? desde : minimo;
  const hastaVisto = filtroAplicado ? hasta : maximo;
  const sensorVisto = filtroAplicado ? sensor : 'todos';
  const cuenta = (d: TimelinePoint) =>
    sensorVisto === 'todos'
      ? d.count
      : ((d as unknown as Record<string, number>)[sensorVisto] ?? 0);

  // Interrupciones de captura, siempre contadas en días. Siguen la selección pero se leen de la
  // serie diaria: con el intervalo por hora, dos horas seguidas en cero no distinguen un sensor
  // caído de una madrugada tranquila, y el bloque declararía cortes que nunca ocurrieron. Un día
  // entero sin un solo evento sí es un corte, porque llegan unos treinta mil por día.
  const outages: { from: string; to: string; days: number }[] = [];
  let run: string[] = [];
  for (const d of timelineBase) {
    if (d.date < desdeVisto || d.date > hastaVisto) continue;
    if (cuenta(d) === 0) run.push(d.date);
    else if (run.length) {
      if (run.length >= 2) {
        outages.push({ from: run[0], to: run[run.length - 1], days: run.length });
      }
      run = [];
    }
  }
  if (run.length >= 2) outages.push({ from: run[0], to: run[run.length - 1], days: run.length });

  return (
    <section className="flex flex-col gap-14">
      <Tooltip content={tip.content} at={tip.at} />

      {/* La presentación: la captura diaria entera, dibujada en puntos, y los cuatro números */}
      <div className="presentacion presentacion-puntos">
        <div className="relative flex flex-col items-center text-center px-5 pt-16 sm:pt-20">
          <span className="insignia section-in">{t.pulse.badge(days)}</span>
          <h1 className="titulo-puntos mt-6 section-in">{t.nav.pulso}</h1>
          <p className="portada-bajada section-in">{t.lead.pulso}</p>
        </div>
        <PuntosDelPulso serie={timelineBase} />
        <div className="relative max-w-5xl mx-auto px-5 pt-10 pb-10 grid grid-cols-2 lg:grid-cols-4 gap-y-10 gap-x-4">
          {tiles.map((tile, i) => (
            <Reveal key={tile.label} delay={i * 80}>
              <div
                className="flex flex-col items-center text-center cursor-default"
                onMouseMove={(e) =>
                  tip.show(
                    e,
                    <div className="max-w-[240px]">
                      <div className="text-[11px] text-white/85 leading-snug">{tile.detail}</div>
                    </div>,
                  )
                }
                onMouseLeave={tip.hide}
              >
                <tile.icon className="w-4 h-4" style={{ color: tile.glow }} />
                <div className="cifra-columna mt-3">
                  <CountUp end={tile.value} />
                </div>
                <div className="text-[12.5px] text-white/75 mt-2">{tile.label}</div>
                <div className="text-[11px] text-white/40 mt-0.5">{tile.sub}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>

      <Reveal>
        <div className="pliego">
          <div className="flex items-end justify-between mb-1 flex-wrap gap-3">
            <div className="flex flex-col gap-3">
              <span className="ceja">{t.pulse.events_short}</span>
              <h2 className="titulo-bloque">{t.pulse.chartTitle}</h2>
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              {sensors.map((s) => (
                <span key={s} className="flex items-center gap-1.5 text-[10px] text-white/45">
                  <span
                    className="w-2 h-2 rounded-sm"
                    style={{ background: SENSOR_COLOR[s] ?? 'var(--ghost-slate)' }}
                  />
                  {s}
                </span>
              ))}
              {/* El rango que se está viendo, no el de la captura entera: si no, el gráfico
                  cambiaría con el filtro y su encabezado seguiría diciendo lo mismo. */}
              <span className="font-data text-[10px] text-white/30">
                {filtroAplicado ? t.footer.range(desde, hasta) : t.footer.range(minimo, maximo)}
                {filtroAplicado && (
                  <span className="ml-2 text-[var(--honey-amber)]/70">{t.pulse.filtered}</span>
                )}
              </span>
            </div>
          </div>

          <div className="mt-5">
            <TimelineControls
              interval={interval}
              sensor={sensor}
              desde={desde}
              hasta={hasta}
              minimo={minimo}
              maximo={maximo}
              onInterval={cambiarIntervalo}
              onSensor={setSensor}
              onRango={(d, h) => {
                setDesde(d);
                setHasta(h);
              }}
              onAtajo={aplicarAtajo}
              atajoActivo={atajoActivo}
              loading={cargando}
            />
          </div>

          {/* El aviso va entre los controles y el gráfico, que es donde mira quien acaba de tocar
              un filtro y no vio cambiar nada. */}
          {problema && (
            <div className="mt-2 flex items-start gap-2 rounded-lg ring-1 ring-[var(--honey-amber)]/25 bg-[var(--honey-amber)]/[0.06] px-3 py-2">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-[1px] text-[var(--honey-amber)]" />
              <div>
                <div className="text-[11px] text-white/80">{t.pulse.filterFailed}</div>
                <div className="text-[10px] text-white/45 mt-0.5 leading-relaxed">{problema}</div>
              </div>
            </div>
          )}

          <div className="relative mt-3">
            <div className="bar-group flex items-end gap-px sm:gap-[2px] h-48 sm:h-60">
              {timeline.map((d) => {
                const empty = d.count === 0;
                return (
                  <div
                    key={d.date}
                    className="bar-item flex-1 flex flex-col justify-end h-full transition-opacity duration-200 cursor-default"
                    onMouseMove={(e) =>
                      tip.show(
                        e,
                        <div className="min-w-[168px]">
                          <div className="text-[11px] text-white/90 first-letter:uppercase">
                            {longDate(d.date)}
                          </div>
                          {empty ? (
                            <div className="text-[10px] text-white/45 mt-1.5 max-w-[190px] leading-snug">
                              {t.pulse.noCapture}
                            </div>
                          ) : (
                            <>
                              <div className="font-data text-[15px] text-white mt-0.5">
                                {n(d.count)}
                              </div>
                              <div className="flex flex-col gap-0.5 mt-1.5">
                                {sensors.map((s) => {
                                  const v = (d as unknown as Record<string, number>)[s] ?? 0;
                                  return (
                                    <span
                                      key={s}
                                      className="flex items-center gap-1.5 text-[10px] text-white/55"
                                    >
                                      <span
                                        className="w-1.5 h-1.5 rounded-sm"
                                        style={{
                                          background: SENSOR_COLOR[s] ?? 'var(--ghost-slate)',
                                        }}
                                      />
                                      {s}
                                      <span className="font-data ml-auto text-white/75">
                                        {n(v)}
                                      </span>
                                    </span>
                                  );
                                })}
                              </div>
                              <div className="text-[9px] text-white/30 mt-1.5">
                                {t.pulse.ofTotal(pct(d.count, overview.events))}
                              </div>
                            </>
                          )}
                        </div>,
                      )
                    }
                    onMouseLeave={tip.hide}
                  >
                    {empty ? (
                      <div className="w-full border-b border-dashed border-white/12" />
                    ) : (
                      sensors.map((s) => {
                        const v = (d as unknown as Record<string, number>)[s] ?? 0;
                        if (!v) return null;
                        return (
                          <div
                            key={s}
                            className="w-full rounded-t-[2px]"
                            style={{
                              height: `${Math.max((v / max) * ALTURA_BARRAS, 1.2)}%`,
                              background: `linear-gradient(180deg, ${
                                SENSOR_COLOR[s] ?? 'var(--ghost-slate)'
                              }, color-mix(in srgb, ${SENSOR_COLOR[s] ?? 'var(--ghost-slate)'} 35%, transparent))`,
                            }}
                          />
                        );
                      })
                    )}
                  </div>
                );
              })}
            </div>
            {pico && pico.count > 0 && !cargando && (
              <ManoAlzada trazos={trazosDelPico} notas={notasDelPico} />
            )}
          </div>

          <div className="text-[10px] text-white/35 mt-2.5 leading-relaxed">
            {t.pulse.chartNote}
          </div>
        </div>
      </Reveal>

      {/* La hora del día: lo que se encuentra es que la curva es plana. El tráfico humano tiene
          horario de oficina; este no, porque del otro lado no hay nadie. */}
      <Reveal>
        <div className="pliego grid lg:grid-cols-[300px_minmax(0,1fr)] gap-8 lg:gap-12">
          <div className="flex flex-col gap-3">
            <span className="ceja">{t.pulse.busiest}</span>
            <div className="flex items-end gap-3 mt-2">
              <span className="numero-puntos">{dec(ratio)}</span>
              <span className="text-[13px] text-white/60 leading-snug pb-2 max-w-[9rem]">
                {t.pulse.ratioLabel}
              </span>
            </div>
            <p className="text-[13px] text-white/55 leading-relaxed">{t.pulse.busiestNote}</p>
          </div>
          <div className="min-w-0">
            <div className="relative mt-1">
              <div className="bar-group flex items-end gap-[2px] sm:gap-[3px] h-28">
                {hourly.map((h) => (
                  <div
                    key={h.hour}
                    className="bar-item flex-1 flex flex-col justify-end h-full transition-opacity duration-200 cursor-default"
                    onMouseMove={(e) =>
                      tip.show(
                        e,
                        <div className="min-w-[150px]">
                          <div className="font-data text-[11px] text-white/90">
                            {String(h.hour).padStart(2, '0')}:00 UTC
                          </div>
                          <div className="font-data text-[15px] text-white mt-0.5">
                            {n(h.count)}
                          </div>
                          <div className="text-[10px] text-white/45">{t.pulse.events_short}</div>
                          <div className="text-[10px] text-white/40 mt-1.5 pt-1.5 border-t border-white/8">
                            {n(h.logins)} {t.pulse.loginsAtThisHour}
                          </div>
                        </div>,
                      )
                    }
                    onMouseLeave={tip.hide}
                  >
                    <div
                      className="w-full rounded-sm transition-all duration-700"
                      style={{
                        height: `${(h.count / maxHour) * ALTURA_HORAS}%`,
                        background:
                          'linear-gradient(180deg, var(--honey-amber), color-mix(in srgb, var(--honey-amber) 30%, transparent))',
                        opacity: 0.6 + (h.count / maxHour) * 0.4,
                      }}
                    />
                  </div>
                ))}
              </div>
              {hourly.length > 0 && ratio > 0 && (
                <ManoAlzada
                  trazos={[
                    {
                      tipo: 'subrayado',
                      x1: 1,
                      x2: 99,
                      y: 100 - (promedioHora / maxHour) * ALTURA_HORAS - 6,
                    },
                  ]}
                  notas={[
                    {
                      x: 99,
                      y: 0,
                      texto: t.pulse.noteFlat(dec(ratio)),
                      alinear: 'derecha',
                      ancho: 470,
                    },
                  ]}
                />
              )}
            </div>
            <div className="flex justify-between font-data text-[9px] text-white/25 mt-1.5">
              <span>00</span>
              <span>06</span>
              <span>12</span>
              <span>18</span>
              <span>23</span>
            </div>

            {/* Los cortes de captura, deducidos de los huecos de la propia serie */}
            <div className="mt-8 pt-5 border-t border-dashed border-white/10">
              <div className="rotulo">{t.pulse.outages}</div>
              {outages.length > 0 ? (
                <>
                  <div className="flex flex-wrap gap-2 mt-3">
                    {outages.map((o) => (
                      <div
                        key={o.from}
                        className="flex items-center gap-3 rounded-full border border-dashed border-white/15 px-3 py-1.5"
                      >
                        <span className="font-data text-[10px] text-white/60">
                          {t.footer.range(o.from.slice(5), o.to.slice(5))}
                        </span>
                        <span className="text-[10px] text-white/35">{t.pulse.days(o.days)}</span>
                      </div>
                    ))}
                  </div>
                  <div className="text-[10px] text-white/40 mt-3 leading-relaxed">
                    {t.pulse.outagesNote}
                  </div>
                </>
              ) : (
                /* Un bloque vacío se lee como algo que falló al cargar. Decir que no hubo cortes es
                 información: significa que el sensor cubrió el período entero. */
                <div className="mt-3 flex items-start gap-2.5 rounded-lg bg-[var(--neural-teal)]/[0.06] ring-1 ring-[var(--neural-teal)]/20 px-3 py-2.5">
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-[1px] text-[var(--neural-teal)]" />
                  <div>
                    <div className="text-[11px] text-white/85">{t.pulse.noOutages}</div>
                    <div className="text-[10px] text-white/40 mt-1 leading-relaxed">
                      {t.pulse.noOutagesNote}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </Reveal>

      {/* Va al final porque es la conclusión: las secciones anteriores describen el volumen, esta
          responde quién lo produce. Solo aparece si el respaldo trae la matriz: un snapshot
          congelado antes de que existiera no la tiene. */}
      {weekly && (
        <Reveal delay={320}>
          <WeekHeatmap data={weekly} />
        </Reveal>
      )}
    </section>
  );
}

/**
 * La captura diaria entera como una pared de puntos: una columna por día, con tantos puntos como
 * proporción de eventos tuvo ese día. Los días sin captura quedan con un solo punto apagado, así el
 * hueco se ve igual que en el gráfico de barras.
 */
function PuntosDelPulso({ serie }: { serie: TimelinePoint[] }) {
  const PASO = 10;
  const FILAS = 26;
  const ancho = Math.max(serie.length, 1) * PASO;
  const alto = FILAS * PASO;
  const max = Math.max(...serie.map((d) => d.count), 1);
  return (
    <svg
      viewBox={`0 0 ${ancho} ${alto}`}
      preserveAspectRatio="xMidYMax slice"
      className="puntos-del-pulso"
      aria-hidden
    >
      {serie.map((d, i) => {
        const cuantos = d.count ? Math.max(1, Math.round((d.count / max) * FILAS)) : 0;
        return (
          <g key={d.date} style={{ '--i': i } as React.CSSProperties}>
            {d.count === 0 ? (
              <circle
                cx={i * PASO + PASO / 2}
                cy={alto - PASO / 2}
                r={1.3}
                className="punto-apagado"
              />
            ) : (
              Array.from({ length: cuantos }, (_, k) => (
                <circle
                  key={k}
                  cx={i * PASO + PASO / 2}
                  cy={alto - PASO / 2 - k * PASO}
                  r={k === cuantos - 1 ? 2.4 : 1.8}
                  className={k === cuantos - 1 ? 'punto-cima' : 'punto-lleno'}
                />
              ))
            )}
          </g>
        );
      })}
    </svg>
  );
}
