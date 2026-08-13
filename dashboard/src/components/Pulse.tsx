import { Activity, Fingerprint, KeyRound, TerminalSquare } from 'lucide-react';
import type { Overview, TimelinePoint } from '../lib/api';
import CountUp from './CountUp';
import Reveal from './Reveal';
import Tooltip, { useTooltip } from './Tooltip';
import { n, pct, dec } from '../lib/format';

const SENSOR_COLOR: Record<string, string> = {
  cowrie: 'var(--honey-amber)',
  dionaea: 'var(--neural-teal)',
};



/** Long date for the tooltip: "lunes, 3 de junio". Reads better than an ISO string. */
function longDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('es-AR', {
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
  timeline,
}: {
  overview: Overview;
  timeline: TimelinePoint[];
}) {
  const tip = useTooltip();
  const days = timeline.filter((t) => t.count > 0).length;
  const perDay = days ? Math.round(overview.events / days) : 0;
  const peak = timeline.reduce((a, b) => (b.count > a.count ? b : a), timeline[0]);

  const tiles = [
    {
      icon: Activity,
      label: 'Eventos capturados',
      value: overview.events,
      sub: `${n(perDay)} por día en promedio`,
      glow: 'var(--honey-amber)',
      detail: `Pico de ${n(peak?.count ?? 0)} eventos el ${peak ? longDate(peak.date) : '—'}.`,
    },
    {
      icon: Fingerprint,
      label: 'Direcciones atacantes',
      value: overview.unique_ips,
      sub: `en ${days} días con captura`,
      glow: 'var(--neural-teal)',
      detail: `Una dirección distinta cada ${Math.round((days * 24 * 60) / (overview.unique_ips || 1))} minutos.`,
    },
    {
      icon: KeyRound,
      label: 'Intentos de acceso',
      value: overview.logins,
      sub: `${n(overview.logins_success)} lograron entrar`,
      glow: 'var(--agent-coral)',
      detail: `${pct(overview.logins_success, overview.logins)}% de los intentos acertó una credencial del señuelo.`,
    },
    {
      icon: TerminalSquare,
      label: 'Comandos ejecutados',
      value: overview.commands,
      sub: 'dentro del señuelo',
      glow: 'var(--honey-amber)',
      detail: `${dec(overview.commands / (overview.logins_success || 1))} comandos por sesión que logró entrar.`,
    },
  ];

  const max = Math.max(...timeline.map((t) => t.count), 1);
  const sensors = Object.keys(overview.by_sensor);

  return (
    <section className="flex flex-col gap-4">
      <Tooltip content={tip.content} at={tip.at} />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {tiles.map((t, i) => (
          <Reveal key={t.label} delay={i * 80}>
            <div
              className="tile rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4 h-full cursor-default"
              onMouseMove={(e) =>
                tip.show(
                  e,
                  <div className="max-w-[240px]">
                    <div className="text-[11px] text-white/85 leading-snug">{t.detail}</div>
                  </div>,
                )
              }
              onMouseLeave={tip.hide}
            >
              <span className="tile-glow" style={{ background: t.glow }} />
              <div className="relative">
                <div className="flex items-center gap-2 text-white/35">
                  <t.icon className="w-3.5 h-3.5" />
                  <span className="text-[9px] uppercase tracking-wider">{t.label}</span>
                </div>
                <div className="font-data text-2xl text-white mt-2">
                  <CountUp end={t.value} />
                </div>
                <div className="text-[10px] text-white/40 mt-1">{t.sub}</div>
              </div>
            </div>
          </Reveal>
        ))}
      </div>

      <Reveal delay={200}>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="flex items-baseline justify-between mb-1 flex-wrap gap-2">
            <span className="text-[9px] uppercase tracking-wider text-white/35">
              Actividad diaria por sensor
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

          <div className="bar-group flex items-end gap-[2px] h-32 mt-3">
            {timeline.map((t) => {
              const empty = t.count === 0;
              return (
                <div
                  key={t.date}
                  className="bar-item flex-1 flex flex-col justify-end h-full transition-opacity duration-200 cursor-default"
                  onMouseMove={(e) =>
                    tip.show(
                      e,
                      <div className="min-w-[168px]">
                        <div className="text-[11px] text-white/90 first-letter:uppercase">{longDate(t.date)}</div>
                        {empty ? (
                          <div className="text-[10px] text-white/45 mt-1.5 max-w-[190px] leading-snug">
                            Sin captura. Interrupción documentada, no ausencia de ataques.
                          </div>
                        ) : (
                          <>
                            <div className="font-data text-[15px] text-white mt-0.5">
                              {n(t.count)}
                            </div>
                            <div className="flex flex-col gap-0.5 mt-1.5">
                              {sensors.map((s) => {
                                const v = (t as unknown as Record<string, number>)[s] ?? 0;
                                return (
                                  <span
                                    key={s}
                                    className="flex items-center gap-1.5 text-[10px] text-white/55"
                                  >
                                    <span
                                      className="w-1.5 h-1.5 rounded-sm"
                                      style={{ background: SENSOR_COLOR[s] ?? 'var(--ghost-slate)' }}
                                    />
                                    {s}
                                    <span className="font-data ml-auto text-white/75">{n(v)}</span>
                                  </span>
                                );
                              })}
                            </div>
                            <div className="text-[9px] text-white/30 mt-1.5">
                              {pct(t.count, overview.events)}% del total capturado
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
                      const v = (t as unknown as Record<string, number>)[s] ?? 0;
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
            Las líneas punteadas son interrupciones de captura documentadas, no ausencia de ataques.
            Pasá el cursor por cualquier día para ver el detalle.
          </div>
        </div>
      </Reveal>
    </section>
  );
}
