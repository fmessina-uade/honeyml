import { useEffect, useState } from 'react';
import { Activity, ArrowRight, ArrowUpRight, Fingerprint, KeyRound, Terminal } from 'lucide-react';
import {
  api,
  type ArchetypeData,
  type FingerprintData,
  type ResumenTriaje,
  type Snapshot,
} from '../../lib/api';
import { compacto, dec, duracion, localeActual, n, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { LECCIONES, SECCIONES, lecciones, type SectionId } from '../lecciones';
import CountUp from '../CountUp';
import Latido from '../Latido';
import Miniatura from '../Miniatura';
import Reveal from '../Reveal';

const MINUTOS_ACTIVO = 10;
const REFRESCO_MS = 15000;

/**
 * La portada del panel: una pantalla de presentación con la escala de la captura, una franja con
 * los cuatro números de lo que llega, el motor trabajando y un recuadro por lección.
 *
 * No agrega datos propios. Cada cifra sale de lo mismo que usa la sección a la que lleva, así la
 * portada no puede decir algo distinto de lo que se encuentra al entrar.
 */
export default function Inicio({
  snapshot,
  familias,
  arquetipos,
  sesiones,
  onIr,
}: {
  snapshot: Snapshot;
  familias: FingerprintData | null;
  arquetipos: ArchetypeData | null;
  sesiones: number;
  onIr: (id: SectionId) => void;
}) {
  const { t } = useI18n();
  const h = t.home;
  const [motor, setMotor] = useState<ResumenTriaje | null>(null);
  const [sinMotor, setSinMotor] = useState(false);
  const [ahora, setAhora] = useState(() => Date.now());

  useEffect(() => {
    let vivo = true;
    const traer = () =>
      api
        .triaje()
        .then((r) => {
          if (!vivo) return;
          setMotor(r);
          setSinMotor(false);
        })
        .catch(() => vivo && setSinMotor(true));
    traer();
    const id = window.setInterval(() => {
      traer();
      setAhora(Date.now());
    }, REFRESCO_MS);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, []);

  const o = snapshot.overview;
  const ultima = motor?.actividad.ultima;
  const hace = ultima ? Math.max(0, (ahora - new Date(ultima).getTime()) / 1000) : null;
  const activo = hace !== null && hace < MINUTOS_ACTIVO * 60;

  const dias = snapshot.timeline.filter((d) => d.count > 0).length;
  const cifras = lecciones(snapshot, familias, arquetipos, sesiones, t);
  const desde = o.first_event
    ? new Date(o.first_event).toLocaleDateString(localeActual(), {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
        timeZone: 'UTC',
      })
    : '—';

  const captura = [
    {
      icono: Activity,
      color: 'var(--honey-amber)',
      valor: o.events,
      rotulo: t.pulse.events,
      sub: t.pulse.inDays(dias),
    },
    {
      icono: Fingerprint,
      color: 'var(--neural-teal)',
      valor: o.unique_ips,
      rotulo: t.pulse.addresses,
      sub: h.distinctOrigins,
    },
    {
      icono: KeyRound,
      color: 'var(--agent-coral)',
      valor: o.logins,
      rotulo: t.pulse.logins,
      sub: t.pulse.gotIn(n(o.logins_success)),
    },
    {
      icono: Terminal,
      color: 'var(--ghost-slate)',
      valor: o.commands,
      rotulo: t.pulse.commands,
      sub: t.pulse.insideDecoy,
    },
  ];

  const titular = [compacto(o.events), h.heroWord];

  return (
    <div className="flex flex-col">
      {/* La presentación: la escala de la captura en grande y por dónde entrar */}
      <section className="portada">
        <div className="portada-fondo" aria-hidden>
          <Hilos />
        </div>
        <div className="portada-velo" aria-hidden />

        <div className="flex-1 flex flex-col items-center justify-center text-center px-5 pt-14 pb-10">
          <span className="insignia section-in">{h.heroBadge(desde)}</span>
          <h1 className="portada-titulo mt-6" aria-label={titular.join(' ')}>
            {titular.map((palabra, i) => (
              <span key={i} aria-hidden>
                <span className="titular-mascara">
                  <span
                    className={i === 0 ? 'degradado' : undefined}
                    style={{ '--d': `${0.15 + i * 0.12}s` } as React.CSSProperties}
                  >
                    {palabra}
                  </span>
                </span>
                {i === 0 && ' '}
              </span>
            ))}
          </h1>
          <p className="portada-bajada section-in">{h.heroSub}</p>
          <div className="flex flex-wrap justify-center gap-3 mt-8 section-in">
            <button className="boton-solido" onClick={() => onIr('triaje')}>
              {h.openEngine}
              <ArrowRight className="w-4 h-4" />
            </button>
            <button className="boton-vidrio" onClick={() => onIr('pulso')}>
              {h.heroTour}
            </button>
          </div>
        </div>

        {/* Las lecciones pasando al pie, como en una landing pasan las marcas que la respaldan */}
        <div className="w-full max-w-5xl mx-auto px-5 pb-9 flex items-center gap-10">
          <p className="hidden md:block shrink-0 max-w-[11rem] text-[13px] leading-snug text-white/50">
            {h.marqueeLead}
          </p>
          <div className="marquesina flex-1 min-w-0">
            <div className="marquesina-pista">
              {[0, 1].map((copia) =>
                LECCIONES.map((id) => {
                  const Icono = SECCIONES[id].icon;
                  return (
                    <button
                      key={`${copia}-${id}`}
                      onClick={() => onIr(id)}
                      aria-hidden={copia === 1 || undefined}
                      tabIndex={copia === 1 ? -1 : undefined}
                      className="group flex items-center gap-3 pr-14 shrink-0"
                    >
                      <span
                        className="vidrio-liquido w-8 h-8 rounded-lg grid place-items-center"
                        style={{ color: SECCIONES[id].color }}
                      >
                        <Icono className="w-4 h-4" />
                      </span>
                      <span className="geist text-[15px] font-semibold tracking-tight text-white/90 group-hover:text-white transition whitespace-nowrap">
                        {t.nav[id]}
                      </span>
                      <span className="font-data text-[12px] text-white/45 whitespace-nowrap">
                        {cifras[id].cifra}
                      </span>
                    </button>
                  );
                }),
              )}
            </div>
          </div>
        </div>
      </section>

      {/* La captura, en cuatro números sueltos */}
      <section className="pt-14 pb-4">
        <Reveal className="flex justify-center">
          <span className="ceja">{h.captureTitle}</span>
        </Reveal>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-y-12 gap-x-4 mt-10">
          {captura.map((c, i) => (
            <Reveal key={c.rotulo} delay={i * 90}>
              <div className="flex flex-col items-center text-center">
                <c.icono className="w-5 h-5" style={{ color: c.color }} />
                <div className="cifra-columna mt-4">
                  <CountUp end={c.valor} />
                </div>
                <div className="text-[13px] text-white/80 mt-2">{c.rotulo}</div>
                <div className="text-[11.5px] text-white/45 mt-0.5 max-w-[15rem]">{c.sub}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* El motor, trabajando ahora mismo */}
      <Reveal className="mt-14">
        <section className="motor escenario relative overflow-hidden">
          <div aria-hidden className="escenario-luz" data-pensando="no" />
          <div className="relative px-5 py-6 sm:px-8 sm:py-7 grid lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] gap-8 lg:gap-12 items-center">
            <div className="flex flex-col gap-5 min-w-0">
              <span className="ceja">{h.engineTitle}</span>
              {motor ? (
                <>
                  <div className="flex items-center gap-2.5">
                    <span className="relative flex w-2.5 h-2.5">
                      {activo && (
                        <span className="absolute inline-flex h-full w-full rounded-full bg-[#ff6b35] opacity-60 animate-ping" />
                      )}
                      <span
                        className="relative inline-flex w-2.5 h-2.5 rounded-full"
                        style={{
                          background: activo ? 'var(--agent-coral)' : 'var(--motor-apagado)',
                        }}
                      />
                    </span>
                    <span className="geist text-[16px] font-medium tracking-tight text-white">
                      {activo ? t.triage.engine.active : t.triage.engine.idle}
                    </span>
                    {hace !== null && (
                      <span className="font-data text-[11px] text-white/45">
                        {t.triage.engine.lastAgo(duracion(hace))}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-end gap-x-4 gap-y-4">
                    {[
                      [n(motor.actividad.ultima_hora), h.lastHour],
                      [
                        motor.conclusion.mediana_s !== null
                          ? duracion(motor.conclusion.mediana_s)
                          : '—',
                        h.toDecision,
                      ],
                      [n(motor.revision.pendientes), h.pending],
                    ].map(([valor, texto], i) => (
                      <div key={texto} className="flex items-end gap-4">
                        {i > 0 && <span className="barra-oblicua" aria-hidden />}
                        <div className="flex items-end gap-2.5">
                          <span className="cifra-fina">{valor}</span>
                          <span className="text-[12px] leading-snug text-white/55 max-w-[7.5em] pb-1">
                            {texto}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="text-[13px] text-white/60 leading-relaxed max-w-[34rem]">
                    {h.engineLine(
                      n(motor.total),
                      pct(motor.copiadas, motor.total, 1),
                      dec(motor.costo_usd, 2),
                    )}
                  </p>
                  <button onClick={() => onIr('triaje')} className="pildora-perilla self-start">
                    <span>{h.openEngine}</span>
                    <span className="perilla" aria-hidden>
                      <ArrowRight className="w-4 h-4" />
                    </span>
                  </button>
                </>
              ) : (
                <p className="text-[13px] text-white/50">
                  {sinMotor ? t.triage.liveOnly : t.loading}
                </p>
              )}
            </div>
            {motor?.actividad.por_minuto?.length ? (
              <div className="min-w-0">
                <Latido serie={motor.actividad.por_minuto} alto={150} />
              </div>
            ) : (
              !motor && <div className="h-[150px] rounded-xl bg-white/[0.02]" />
            )}
          </div>
        </section>
      </Reveal>

      {/* Por dónde seguir: un recuadro por lección, con su gráfico como imagen */}
      <section className="mt-16">
        <Reveal className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-3">
            <span className="ceja">{h.marqueeLead}</span>
            <h2 className="titulo-bloque">{h.learnTitle}</h2>
          </div>
          <span className="text-[12px] text-white/45">{h.learnHint}</span>
        </Reveal>
        <Reveal delay={80} className="bento mt-7">
          {LECCIONES.map((id) => (
            <button
              key={id}
              data-celda={id}
              data-forma={id === 'pulso' || id === 'origen' ? 'alta' : 'ancha'}
              onClick={() => onIr(id)}
              className="lamina"
              style={{ '--tono': SECCIONES[id].color } as React.CSSProperties}
            >
              <span className="lamina-arte" aria-hidden>
                <Miniatura
                  id={id}
                  color={SECCIONES[id].color}
                  snapshot={snapshot}
                  familias={familias}
                  arquetipos={arquetipos}
                />
              </span>
              <span className="ceja lamina-ceja">{t.nav[id]}</span>
              <ArrowUpRight className="lamina-flecha w-4 h-4" aria-hidden />
              <span className="lamina-pie flex flex-col gap-1.5">
                <span className="lamina-cifra" style={{ color: SECCIONES[id].color }}>
                  {cifras[id].cifra}
                </span>
                <span className="text-[12px] text-white/60 leading-snug max-w-[28rem]">
                  {cifras[id].texto}
                </span>
              </span>
            </button>
          ))}
        </Reveal>
      </section>
    </div>
  );
}

/**
 * Los hilos del fondo de la portada: trazos gruesos que se cruzan. El volumen sale de capas sobre
 * el mismo trazo, una sombra del lado contrario a la luz y un brillo del lado de la luz, corridas
 * hacia donde da. Son dibujo puro, sin imagen ni video externos.
 */
function Hilos() {
  const hilos = [
    {
      d: 'M-160 720 C 220 520, 460 880, 800 640 S 1280 330, 1620 500',
      ancho: 130,
      grad: 'hilo-a',
      grupo: 'hilos-a',
      luz: [0, -1],
    },
    {
      d: 'M-120 170 C 240 40, 430 360, 720 250 S 1160 30, 1580 140',
      ancho: 92,
      grad: 'hilo-b',
      grupo: 'hilos-b',
      luz: [0, -1],
    },
    {
      d: 'M1180 -80 C 1060 220, 1420 360, 1290 640 S 1100 980, 1320 1040',
      ancho: 110,
      grad: 'hilo-c',
      grupo: 'hilos-b',
      luz: [-1, 0],
    },
    {
      d: 'M180 -60 C 40 180, 300 300, 160 520 S -40 860, 120 1000',
      ancho: 84,
      grad: 'hilo-c',
      grupo: 'hilos-a',
      luz: [-1, 0],
    },
  ];
  const corrida = (luz: number[], k: number) => `translate(${luz[0] * k} ${luz[1] * k})`;
  return (
    <svg
      viewBox="0 0 1440 900"
      preserveAspectRatio="xMidYMid slice"
      className="absolute inset-0 w-full h-full"
    >
      <defs>
        <linearGradient id="hilo-a" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#0d1117" />
          <stop offset="0.4" stopColor="#3a4658" />
          <stop offset="0.75" stopColor="#ff6b35" />
          <stop offset="1" stopColor="#d4860a" />
        </linearGradient>
        <linearGradient id="hilo-b" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#d4860a" stopOpacity="0.85" />
          <stop offset="0.5" stopColor="#00b894" stopOpacity="0.85" />
          <stop offset="1" stopColor="#0d1117" />
        </linearGradient>
        <linearGradient id="hilo-c" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0d1117" />
          <stop offset="0.55" stopColor="#5b6b80" />
          <stop offset="1" stopColor="#d4860a" stopOpacity="0.85" />
        </linearGradient>
        <filter id="hilo-borde" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur stdDeviation="1.6" />
        </filter>
        <filter id="hilo-difuso" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur stdDeviation="10" />
        </filter>
        <filter id="hilo-brillo" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur stdDeviation="4" />
        </filter>
      </defs>
      {hilos.map((h, i) => (
        <g key={i} className={h.grupo} fill="none" strokeLinecap="round">
          <path
            d={h.d}
            className="hilo-sombra"
            strokeWidth={h.ancho + 26}
            transform={corrida(h.luz, -h.ancho * 0.12)}
            filter="url(#hilo-difuso)"
          />
          <path
            d={h.d}
            stroke={`url(#${h.grad})`}
            strokeWidth={h.ancho}
            filter="url(#hilo-borde)"
          />
          <path
            d={h.d}
            className="hilo-nucleo"
            strokeWidth={h.ancho * 0.5}
            transform={corrida(h.luz, -h.ancho * 0.24)}
            filter="url(#hilo-difuso)"
          />
          <path
            d={h.d}
            stroke="#ffffff"
            strokeOpacity="0.12"
            strokeWidth={h.ancho * 0.5}
            transform={corrida(h.luz, h.ancho * 0.12)}
            filter="url(#hilo-difuso)"
          />
          <path
            d={h.d}
            stroke="#ffffff"
            strokeOpacity="0.32"
            strokeWidth={h.ancho * 0.12}
            transform={corrida(h.luz, h.ancho * 0.3)}
            filter="url(#hilo-brillo)"
          />
        </g>
      ))}
    </svg>
  );
}
