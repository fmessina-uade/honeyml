import { useEffect, useState } from 'react';
import { Activity, Fingerprint, KeyRound, TerminalSquare } from 'lucide-react';
import type { HourPoint, Overview, TimelinePoint } from '../../lib/api';
import CountUp from '../CountUp';
import Reveal from '../Reveal';
import Tooltip, { useTooltip } from '../Tooltip';
import { n, pct, dec } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import TimelineControls, { type Interval, type Sensor } from '../TimelineControls';
import { api } from '../../lib/api';

const SENSOR_COLOR: Record<string, string> = {
  cowrie: 'var(--honey-amber)',
  dionaea: 'var(--neural-teal)',
};

/** Long date for the tooltip: "lunes, 3 de junio". Reads better than an ISO string. */
function longDate(iso: string, lang: 'es' | 'en'): string {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(lang === 'en' ? 'en-GB' : 'es-AR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  });
}

/**
 * The opening: raw scale. A machine nobody advertised, under constant attack.
 *
 * The daily bars are split by sensor rather than totalled. That is what makes the Dionaea
 * outage legible instead of looking like a drop in attacks.
 */
export default function Pulse({
  overview,
  timeline: timelineBase,
  hourly,
}: {
  overview: Overview;
  timeline: TimelinePoint[];
  hourly: HourPoint[];
}) {
  const { t, lang } = useI18n();
  const tip = useTooltip();

  // La serie del snapshot es la vista por defecto. En cuanto se toca un filtro se pide una serie
  // nueva a la API y se muestra esa; volver a "por día" y "ambos" recupera la original sin pedir
  // nada, que es la combinación que el snapshot ya trae.
  const [interval, setInterval] = useState<Interval>('day');
  const [sensor, setSensor] = useState<Sensor>('todos');
  const [serie, setSerie] = useState<TimelinePoint[] | null>(null);
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    if (interval === 'day' && sensor === 'todos') {
      setSerie(null);
      return;
    }
    let vigente = true;
    setCargando(true);
    api
      .timeline(interval, sensor)
      .then((d) => {
        // Una respuesta que llega tarde, después de que el usuario cambió de filtro otra vez, no
        // debe pisar a la que corresponde al filtro actual.
        if (vigente) setSerie(d);
      })
      .catch(() => vigente && setSerie(null))
      .finally(() => vigente && setCargando(false));
    return () => {
      vigente = false;
    };
  }, [interval, sensor]);

  const timeline = serie ?? timelineBase;
  const days = timeline.filter((d) => d.count > 0).length;
  const perDay = days ? Math.round(overview.events / days) : 0;
  const peak = timeline.reduce((a, b) => (b.count > a.count ? b : a), timeline[0]);

  const tiles = [
    {
      icon: Activity,
      label: t.pulse.events,
      value: overview.events,
      sub: t.pulse.perDay(n(perDay)),
      glow: 'var(--honey-amber)',
      detail: t.pulse.peak(n(peak?.count ?? 0), peak ? longDate(peak.date, lang) : '—'),
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
  const maxHour = Math.max(...hourly.map((h) => h.count), 1);
  const minHour = hourly.length ? Math.min(...hourly.map((h) => h.count)) : 0;
  // peak-to-trough: a human rhythm sits well above 3x, automation stays near 1
  const ratio = minHour > 0 ? maxHour / minHour : 0;

  // outages read straight off the timeline, so the panel can never disagree with its own chart
  const outages: { from: string; to: string; days: number }[] = [];
  let run: string[] = [];
  for (const d of timeline) {
    if (d.count === 0) run.push(d.date);
    else if (run.length) {
      if (run.length >= 2) {
        outages.push({ from: run[0], to: run[run.length - 1], days: run.length });
      }
      run = [];
    }
  }
  if (run.length >= 2) outages.push({ from: run[0], to: run[run.length - 1], days: run.length });
  const sensors = Object.keys(overview.by_sensor);

  return (
    <section className="flex flex-col gap-4">
      <Tooltip content={tip.content} at={tip.at} />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {tiles.map((tile, i) => (
          <Reveal key={tile.label} delay={i * 80}>
            <div
              className="tile rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4 h-full cursor-default"
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
              <span className="tile-glow" style={{ background: tile.glow }} />
              <div className="relative">
                <div className="flex items-center gap-2 text-white/35">
                  <tile.icon className="w-3.5 h-3.5" />
                  <span className="text-[9px] uppercase tracking-wider">{tile.label}</span>
                </div>
                <div className="font-data text-2xl text-white mt-2">
                  <CountUp end={tile.value} />
                </div>
                <div className="text-[10px] text-white/40 mt-1">{tile.sub}</div>
              </div>
            </div>
          </Reveal>
        ))}
      </div>

      <Reveal delay={200}>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="flex items-baseline justify-between mb-1 flex-wrap gap-2">
            <span className="text-[9px] uppercase tracking-wider text-white/35">
              {t.pulse.chartTitle}
            </span>
            <div className="flex items-center gap-3">
              {sensors.map((s) => (
                <span key={s} className="flex items-center gap-1.5 text-[10px] text-white/45">
                  <span
                    className="w-2 h-2 rounded-sm"
                    style={{ background: SENSOR_COLOR[s] ?? 'var(--ghost-slate)' }}
                  />
                  {s}
                </span>
              ))}
              <span className="font-data text-[10px] text-white/30">
                {overview.first_event?.slice(0, 10)} → {overview.last_event?.slice(0, 10)}
              </span>
            </div>
          </div>

          <div className="mt-2">
            <TimelineControls
              interval={interval}
              sensor={sensor}
              onInterval={setInterval}
              onSensor={setSensor}
              loading={cargando}
            />
          </div>

          <div className="bar-group flex items-end gap-[2px] h-32 mt-3">
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
                          {longDate(d.date, lang)}
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
                                    <span className="font-data ml-auto text-white/75">{n(v)}</span>
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
                          className="w-full rounded-[1px]"
                          style={{
                            height: `${Math.max((v / max) * 100, 1.5)}%`,
                            background: SENSOR_COLOR[s] ?? 'var(--ghost-slate)',
                          }}
                        />
                      );
                    })
                  )}
                </div>
              );
            })}
          </div>

          <div className="text-[10px] text-white/35 mt-2.5 leading-relaxed">
            {t.pulse.chartNote}
          </div>
        </div>
      </Reveal>

      {/* Hour of day: the flat curve is the finding. Human traffic has office hours; this does
          not, because there is nobody on the other side. */}
      <Reveal delay={260}>
        <div className="grid lg:grid-cols-[1fr_320px] gap-3">
          <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
            <div className="flex items-baseline justify-between gap-3 flex-wrap">
              <span className="text-[9px] uppercase tracking-wider text-white/35">
                {t.pulse.busiest}
              </span>
              <span className="font-data text-[10px] text-white/30">
                {t.pulse.ratio(dec(ratio))}
              </span>
            </div>

            <div className="bar-group flex items-end gap-[3px] h-20 mt-3">
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
                        <div className="font-data text-[15px] text-white mt-0.5">{n(h.count)}</div>
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
                      height: `${(h.count / maxHour) * 100}%`,
                      background: 'var(--honey-amber)',
                      opacity: 0.55 + (h.count / maxHour) * 0.45,
                    }}
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-between font-data text-[9px] text-white/25 mt-1.5">
              <span>00</span>
              <span>06</span>
              <span>12</span>
              <span>18</span>
              <span>23</span>
            </div>
            <div className="text-[10px] text-white/40 mt-2.5 leading-relaxed">
              {t.pulse.busiestNote}
            </div>
          </div>

          {/* Outages, derived from the gaps in the timeline itself */}
          <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
            <div className="text-[9px] uppercase tracking-wider text-white/35">
              {t.pulse.outages}
            </div>
            <div className="flex flex-col gap-2 mt-3">
              {outages.map((o) => (
                <div
                  key={o.from}
                  className="flex items-center justify-between gap-2 rounded-lg bg-white/[0.02] ring-1 ring-white/5 px-2.5 py-2"
                >
                  <span className="font-data text-[10px] text-white/60">
                    {o.from.slice(5)} → {o.to.slice(5)}
                  </span>
                  <span className="text-[10px] text-white/35">{t.pulse.days(o.days)}</span>
                </div>
              ))}
            </div>
            <div className="text-[10px] text-white/40 mt-3 leading-relaxed">
              {t.pulse.outagesNote}
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
}
