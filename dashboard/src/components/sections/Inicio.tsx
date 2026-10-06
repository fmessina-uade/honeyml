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
          <Colmena />
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

// Generador pseudoaleatorio con semilla: la colmena se ve igual en cada carga y en cada captura.
function semilla(n: number) {
  let a = n;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Los nodos de cada celda, en el orden del logo: arriba a la izquierda coral, arriba a la derecha
// gris pizarra, a la derecha verde, y lo mismo invertido abajo.
const NODOS = ['nodo-gris', 'nodo-verde', 'nodo-coral', 'nodo-gris', 'nodo-verde', 'nodo-coral'];

/**
 * El fondo de la portada es la marca extendida: un panal de hexágonos con los nodos de colores en
 * los vértices, como en el logo. Algunas celdas se encienden con el centro ámbar y se unen entre sí
 * con un trazo que va pasando, la parte de red neuronal de la marca. Es dibujo puro, sin imágenes.
 */
function Colmena() {
  const ANCHO = 1440;
  const ALTO = 900;
  const r = 58;
  const h = Math.sqrt(3) * r;
  const azar = semilla(7);
  const vertices = (cx: number, cy: number, k: number) =>
    Array.from({ length: 6 }, (_, i) => {
      const a = (Math.PI / 3) * i;
      return [cx + k * Math.cos(a), cy + k * Math.sin(a)] as const;
    });
  const camino = (cx: number, cy: number, k: number) =>
    `M${vertices(cx, cy, k)
      .map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`)
      .join(' L')}Z`;

  const celdas: { cx: number; cy: number; viva: boolean; demora: number }[] = [];
  for (let col = -1; col * 1.5 * r < ANCHO + r; col++) {
    for (let fila = -1; fila * h < ALTO + h; fila++) {
      const cx = col * 1.5 * r;
      const cy = fila * h + (col % 2 ? h / 2 : 0);
      celdas.push({ cx, cy, viva: azar() < 0.09, demora: azar() * 6 });
    }
  }
  const vivas = celdas.filter((c) => c.viva);
  // Cada celda encendida se une con la encendida más cercana: la red se arma sola con lo que tocó.
  const enlaces = vivas.flatMap((a, i) => {
    const b = vivas
      .filter((_, j) => j !== i)
      .sort(
        (x, y) => Math.hypot(x.cx - a.cx, x.cy - a.cy) - Math.hypot(y.cx - a.cx, y.cy - a.cy),
      )[0];
    return b && a.cx < b.cx ? [{ a, b }] : [];
  });

  return (
    <svg
      viewBox={`0 0 ${ANCHO} ${ALTO}`}
      preserveAspectRatio="xMidYMid slice"
      className="colmena absolute inset-0 w-full h-full"
    >
      <g className="colmena-deriva">
        {celdas.map((c, i) => (
          <g key={i}>
            <path d={camino(c.cx, c.cy, r * 0.86)} className="celda-borde" />
            {vertices(c.cx, c.cy, r * 0.86).map(([x, y], k) =>
              (i + k) % 3 === 0 ? (
                <circle key={k} cx={x} cy={y} r={3.4} className={NODOS[k]} />
              ) : null,
            )}
          </g>
        ))}
        {enlaces.map(({ a, b }, i) => (
          <line key={i} x1={a.cx} y1={a.cy} x2={b.cx} y2={b.cy} className="colmena-enlace" />
        ))}
        {vivas.map((c, i) => (
          <g
            key={i}
            className="celda-viva"
            style={{ '--d': `${c.demora.toFixed(2)}s` } as React.CSSProperties}
          >
            <path d={camino(c.cx, c.cy, r * 0.6)} className="celda-centro" />
            <path d={camino(c.cx, c.cy, r * 0.3)} className="celda-nucleo" />
            <circle cx={c.cx} cy={c.cy} r={4} className="celda-punto" />
          </g>
        ))}
      </g>
    </svg>
  );
}
