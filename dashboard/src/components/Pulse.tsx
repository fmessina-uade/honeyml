import { Activity, Fingerprint, KeyRound, TerminalSquare } from 'lucide-react';
import type { Overview, TimelinePoint } from '../lib/api';
import CountUp from './CountUp';
import Reveal from './Reveal';

/**
 * The opening: raw scale. A machine nobody advertised, under constant attack.
 * The lesson here is that exposure alone is enough to be attacked.
 */
export default function Pulse({
  overview,
  timeline,
}: {
  overview: Overview;
  timeline: TimelinePoint[];
}) {
  const days = timeline.filter((t) => t.count > 0).length;
  const perDay = days ? Math.round(overview.events / days) : 0;

  const tiles = [
    {
      icon: Activity,
      label: 'Eventos capturados',
      value: overview.events,
      sub: `${perDay.toLocaleString('es-AR')} por día en promedio`,
      glow: 'var(--honey-amber)',
    },
    {
      icon: Fingerprint,
      label: 'Direcciones atacantes',
      value: overview.unique_ips,
      sub: `en ${days} días con captura`,
      glow: 'var(--neural-teal)',
    },
    {
      icon: KeyRound,
      label: 'Intentos de acceso',
      value: overview.logins,
      sub: `${overview.logins_success.toLocaleString('es-AR')} lograron entrar`,
      glow: 'var(--agent-coral)',
    },
    {
      icon: TerminalSquare,
      label: 'Comandos ejecutados',
      value: overview.commands,
      sub: 'dentro del señuelo',
      glow: 'var(--honey-amber)',
    },
  ];

  const max = Math.max(...timeline.map((t) => t.count), 1);

  return (
    <section className="flex flex-col gap-4">
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {tiles.map((t, i) => (
          <Reveal key={t.label} delay={i * 80}>
            <div className="tile rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4 h-full">
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
          <div className="flex items-baseline justify-between mb-3">
            <span className="text-[9px] uppercase tracking-wider text-white/35">
              Actividad diaria
            </span>
            <span className="font-data text-[10px] text-white/35">
              {overview.first_event?.slice(0, 10)} a {overview.last_event?.slice(0, 10)}
            </span>
          </div>
          <div className="flex items-end gap-[2px] h-28">
            {timeline.map((t, i) => (
              <div
                key={t.date}
                title={`${t.date}: ${t.count.toLocaleString('es-AR')} eventos`}
                className="flex-1 rounded-sm opacity-80 hover:opacity-100 transition-all duration-500"
                style={{
                  height: `${Math.max((t.count / max) * 100, t.count ? 2 : 0)}%`,
                  background: t.count ? 'var(--honey-amber)' : 'transparent',
                  borderBottom: t.count ? 'none' : '1px solid rgba(255,255,255,0.08)',
                  transitionDelay: `${Math.min(i * 12, 600)}ms`,
                }}
              />
            ))}
          </div>
          <div className="text-[10px] text-white/35 mt-2 leading-relaxed">
            Los huecos corresponden a interrupciones de captura documentadas, no a ausencia de
            ataques.
          </div>
        </div>
      </Reveal>
    </section>
  );
}
