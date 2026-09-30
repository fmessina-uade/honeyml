import type { ReactNode } from 'react';
import type { ProtocolDetail } from '../../lib/api';
import Reveal from '../Reveal';
import Tooltip, { useTooltip } from '../Tooltip';
import ManoAlzada, { type Nota, type Trazo } from '../ManoAlzada';
import { compacto, n, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { useAncho } from '../../lib/useAncho';

/**
 * Qué es cada servicio expuesto, y por qué alguien golpea ahí. El punto de la sección es que SSH
 * es la puerta que todo el mundo se acuerda de cerrar, y las otras son las que quedan abiertas.
 */
const PROTOCOL_INFO: Record<string, { name: string; what: string; why: string; color: string }> = {
  smbd: {
    name: 'SMB',
    what: 'Compartir archivos e impresoras en redes Windows.',
    why: 'Es el protocolo de WannaCry y NotPetya. Nunca debería estar expuesto a internet, y sin embargo sigue siendo el más golpeado: los gusanos de 2017 todavía circulan buscando equipos sin parchear.',
    color: 'var(--agent-coral)',
  },
  httpd: {
    name: 'HTTP',
    what: 'El protocolo de la web.',
    why: 'Lo recorren escáneres buscando paneles de administración, archivos de configuración olvidados y vulnerabilidades conocidas en gestores de contenido.',
    color: 'var(--honey-amber)',
  },
  mysqld: {
    name: 'MySQL',
    what: 'Base de datos abierta al puerto 3306.',
    why: 'Una base de datos accesible desde internet es acceso directo a los datos, sin necesidad de vulnerar el sistema operativo. Se prueban credenciales por defecto.',
    color: 'var(--neural-teal)',
  },
  mssqld: {
    name: 'MSSQL',
    what: 'Base de datos de Microsoft en el puerto 1433.',
    why: 'El usuario "sa" es el administrador y existe en toda instalación. Es el equivalente a root: no hay que adivinar el nombre.',
    color: 'var(--violeta)',
  },
  ftpd: {
    name: 'FTP',
    what: 'Transferencia de archivos, sin cifrado.',
    why: 'Las credenciales viajan en texto plano. Se prueba el acceso anónimo, todavía habilitado por defecto en muchos servidores viejos.',
    color: 'var(--ghost-slate)',
  },
  epmapper: {
    name: 'MSRPC',
    what: 'Localizador de servicios remotos de Windows, puerto 135.',
    why: 'Sirve para enumerar qué servicios corren en el equipo. Es reconocimiento previo a elegir un exploit.',
    color: 'var(--celeste)',
  },
  ftpdatalisten: {
    name: 'FTP (canal de datos)',
    what: 'Conexión secundaria que abre FTP para transferir el archivo.',
    why: 'No es un vector propio: aparece como consecuencia de la actividad en FTP. Se muestra para que el total cierre.',
    color: 'rgba(148,163,184,0.5)',
  },
};

const PROTOCOL_INFO_EN: Record<string, { name: string; what: string; why: string; color: string }> =
  {
    smbd: {
      name: 'SMB',
      what: 'File and printer sharing on Windows networks.',
      why: 'It is the protocol of WannaCry and NotPetya. It should never be exposed to the internet, and yet it remains the most hammered: the worms of 2017 are still circulating, looking for unpatched machines.',
      color: 'var(--agent-coral)',
    },
    httpd: {
      name: 'HTTP',
      what: 'The protocol of the web.',
      why: 'Scanners sweep it looking for admin panels, forgotten configuration files and known vulnerabilities in content management systems.',
      color: 'var(--honey-amber)',
    },
    mysqld: {
      name: 'MySQL',
      what: 'A database open on port 3306.',
      why: 'A database reachable from the internet is direct access to the data, with no need to breach the operating system. Default credentials get tried.',
      color: 'var(--neural-teal)',
    },
    mssqld: {
      name: 'MSSQL',
      what: "Microsoft's database on port 1433.",
      why: 'The "sa" user is the administrator and exists on every install. It is the equivalent of root: there is no name to guess.',
      color: 'var(--violeta)',
    },
    ftpd: {
      name: 'FTP',
      what: 'File transfer, unencrypted.',
      why: 'Credentials travel in plain text. Anonymous access gets tried, still enabled by default on many old servers.',
      color: 'var(--ghost-slate)',
    },
    epmapper: {
      name: 'MSRPC',
      what: "Windows' remote service locator, port 135.",
      why: 'It is used to enumerate which services run on the machine. This is reconnaissance before choosing an exploit.',
      color: 'var(--celeste)',
    },
    ftpdatalisten: {
      name: 'FTP (data channel)',
      what: 'The secondary connection FTP opens to transfer the file.',
      why: 'Not a vector of its own: it appears as a consequence of FTP activity. Shown so the totals add up.',
      color: 'rgba(148,163,184,0.5)',
    },
  };

type Info = { name: string; what: string; why: string; color: string };

/** El nombre con que se conoce un servicio del sensor ("smbd" es SMB). */
export const nombreDelServicio = (protocolo: string) => PROTOCOL_INFO[protocolo]?.name ?? protocolo;

/**
 * Direcciones contra eventos por dirección, las dos en escala logarítmica, con una burbuja por
 * servicio del tamaño de su volumen.
 *
 * Las diagonales unen los puntos de igual volumen total: dos servicios sobre la misma diagonal
 * recibieron la misma cantidad de eventos, y aun así uno puede estar arriba a la izquierda (pocas
 * máquinas insistiendo) y el otro abajo a la derecha (muchas, de pasada). Es la lectura que la
 * sección quiere dejar, puesta en geometría.
 */
function Dispersion({
  vectores,
  info,
  insistente,
  disperso,
  mostrarContraste,
  onPasar,
  onSalir,
}: {
  vectores: ProtocolDetail[];
  info: (d: ProtocolDetail) => Info;
  insistente?: ProtocolDetail;
  disperso?: ProtocolDetail;
  mostrarContraste: boolean;
  onPasar: (e: React.MouseEvent, d: ProtocolDetail) => void;
  onSalir: () => void;
}) {
  const { t } = useI18n();
  const { ref, ancho } = useAncho<HTMLDivElement>();
  const puntos = vectores.filter((d) => d.sources > 0 && d.count > 0);
  const angosto = ancho > 0 && ancho < 520;
  const alto = angosto ? 250 : 300;
  const M = { izq: 44, der: 16, arr: 14, aba: 32 };

  if (!puntos.length) return <div ref={ref} />;

  const lx = puntos.map((d) => Math.log10(d.sources));
  const ly = puntos.map((d) => Math.log10(d.count / d.sources));
  // Un tercio de década de margen a cada lado, para que ninguna burbuja quede cortada por el borde.
  const dx0 = Math.min(...lx) - 0.35;
  const dx1 = Math.max(...lx) + 0.35;
  const dy0 = Math.min(...ly) - 0.35;
  const dy1 = Math.max(...ly) + 0.45;
  const anchoUtil = Math.max(ancho - M.izq - M.der, 1);
  const altoUtil = alto - M.arr - M.aba;
  const sx = (v: number) => M.izq + ((v - dx0) / (dx1 - dx0)) * anchoUtil;
  const sy = (v: number) => alto - M.aba - ((v - dy0) / (dy1 - dy0)) * altoUtil;

  const decadas = (a: number, b: number) =>
    Array.from({ length: Math.floor(b) - Math.ceil(a) + 1 }, (_, i) => Math.ceil(a) + i);
  const ticksX = decadas(dx0, dx1);
  const ticksY = decadas(dy0, dy1);
  const diagonales = decadas(dx0 + dy0, dx1 + dy1);
  // En pantallas angostas una diagonal de cada dos, para que las etiquetas no se encimen.
  const diagonalesVisibles = angosto ? diagonales.filter((_, i) => i % 2 === 0) : diagonales;

  const maxVolumen = Math.max(...puntos.map((d) => d.count));
  const radio = (d: ProtocolDetail) => 5 + Math.sqrt(d.count / maxVolumen) * (angosto ? 15 : 22);

  const pos = (d: ProtocolDetail) => ({
    cx: sx(Math.log10(d.sources)),
    cy: sy(Math.log10(d.count / d.sources)),
    r: radio(d),
  });

  // Cada etiqueta prueba a la derecha de su burbuja, después a la izquierda, arriba y abajo, y se
  // queda con el primer lugar que no pisa a otra. Dos servicios pueden caer casi en el mismo punto
  // (pasa con los de pocas direcciones y pocos eventos) y sus nombres no se tienen que encimar.
  const ocupadas: { x1: number; x2: number; y1: number; y2: number }[] = [];
  const etiquetas = new Map<string, { x: number; y: number; ancla: 'start' | 'end' | 'middle' }>();
  for (const d of [...puntos].sort((a, b) => b.count - a.count)) {
    const { cx, cy, r } = pos(d);
    const w = info(d).name.length * 7 + 4;
    const opciones = [
      { x: cx + r + 6, y: cy + 3.5, ancla: 'start' as const, x1: cx + r + 4, x2: cx + r + 6 + w },
      { x: cx - r - 6, y: cy + 3.5, ancla: 'end' as const, x1: cx - r - 6 - w, x2: cx - r - 4 },
      { x: cx, y: cy - r - 5, ancla: 'middle' as const, x1: cx - w / 2, x2: cx + w / 2 },
      { x: cx, y: cy + r + 12, ancla: 'middle' as const, x1: cx - w / 2, x2: cx + w / 2 },
    ];
    const libre =
      opciones.find((o) => {
        const caja = { x1: o.x1, x2: o.x2, y1: o.y - 9, y2: o.y + 3 };
        const adentro = caja.x1 >= 0 && caja.x2 <= ancho;
        const choca = ocupadas.some(
          (b) => caja.x1 < b.x2 && caja.x2 > b.x1 && caja.y1 < b.y2 && caja.y2 > b.y1,
        );
        return adentro && !choca;
      }) ?? opciones[0];
    ocupadas.push({ x1: libre.x1, x2: libre.x2, y1: libre.y - 9, y2: libre.y + 3 });
    etiquetas.set(d.protocol, { x: libre.x, y: libre.y, ancla: libre.ancla });
  }

  // Las anotaciones van en porcentaje del contenedor, así que se traducen desde los píxeles.
  const trazos: Trazo[] = [];
  const notas: Nota[] = [];
  if (mostrarContraste && ancho > 0 && insistente && disperso && insistente !== disperso) {
    for (const [d, lado, texto] of [
      [insistente, 'derecha', t.protocols.noteWorm],
      [disperso, 'izquierda', t.protocols.noteScan],
    ] as const) {
      const { cx, cy, r } = pos(d);
      trazos.push({
        tipo: 'elipse',
        x: (cx / ancho) * 100,
        y: (cy / alto) * 100,
        ancho: ((2 * r + 18) / ancho) * 100,
        alto: ((2 * r + 18) / alto) * 100,
      });
      notas.push({
        x: ((lado === 'derecha' ? cx + r + 12 : cx - r - 12) / ancho) * 100,
        y: (Math.max(cy - r - 34, 0) / alto) * 100,
        texto,
        alinear: lado === 'derecha' ? 'izquierda' : 'derecha',
        ancho: angosto ? 150 : 210,
      });
    }
  }

  return (
    <div ref={ref} className="relative w-full" style={{ height: alto }}>
      {ancho > 0 && (
        <svg width={ancho} height={alto} className="absolute inset-0 overflow-visible">
          {/* la grilla, en décadas */}
          {ticksX.map((k) => (
            <g key={`x${k}`}>
              <line
                x1={sx(k)}
                x2={sx(k)}
                y1={M.arr}
                y2={alto - M.aba}
                stroke="rgb(var(--tinta) / 0.05)"
              />
              <text
                x={sx(k)}
                y={alto - M.aba + 14}
                textAnchor="middle"
                className="font-data"
                fontSize={9}
                fill="rgb(var(--tinta) / 0.3)"
              >
                {compacto(10 ** k)}
              </text>
            </g>
          ))}
          {ticksY.map((k) => (
            <g key={`y${k}`}>
              <line
                x1={M.izq}
                x2={ancho - M.der}
                y1={sy(k)}
                y2={sy(k)}
                stroke="rgb(var(--tinta) / 0.05)"
              />
              <text
                x={M.izq - 8}
                y={sy(k) + 3}
                textAnchor="end"
                className="font-data"
                fontSize={9}
                fill="rgb(var(--tinta) / 0.3)"
              >
                {compacto(10 ** k)}
              </text>
            </g>
          ))}

          {/* diagonales de volumen constante */}
          {diagonalesVisibles.map((k) => {
            const xa = Math.max(dx0, k - dy1);
            const xb = Math.min(dx1, k - dy0);
            if (xa >= xb) return null;
            const p1 = { x: sx(xa), y: sy(k - xa) };
            const p2 = { x: sx(xb), y: sy(k - xb) };
            const angulo = (Math.atan2(p2.y - p1.y, p2.x - p1.x) * 180) / Math.PI;
            const et = { x: p1.x + (p2.x - p1.x) * 0.18, y: p1.y + (p2.y - p1.y) * 0.18 };
            // La etiqueta se omite si no entra antes del borde derecho: cortada no se lee.
            const conEtiqueta = et.x + 64 < ancho;
            return (
              <g key={`d${k}`}>
                <line
                  x1={p1.x}
                  y1={p1.y}
                  x2={p2.x}
                  y2={p2.y}
                  stroke="rgba(212,134,10,0.16)"
                  strokeDasharray="3 5"
                />
                {conEtiqueta && (
                  <text
                    x={et.x}
                    y={et.y - 4}
                    transform={`rotate(${angulo} ${et.x} ${et.y - 4})`}
                    className="font-data"
                    fontSize={8.5}
                    fill="rgba(212,134,10,0.45)"
                  >
                    {t.protocols.isoLabel(compacto(10 ** k))}
                  </text>
                )}
              </g>
            );
          })}

          {/* títulos de los ejes */}
          <text
            x={ancho - M.der}
            y={alto - 4}
            textAnchor="end"
            fontSize={9.5}
            fill="rgb(var(--tinta) / 0.4)"
          >
            {t.protocols.axisX}
          </text>
          <text x={M.izq + 4} y={M.arr + 10} fontSize={9.5} fill="rgb(var(--tinta) / 0.4)">
            {t.protocols.axisY}
          </text>

          {/* una burbuja por servicio, las chicas encima de las grandes */}
          {[...puntos]
            .sort((a, b) => b.count - a.count)
            .map((d) => {
              const { cx, cy, r } = pos(d);
              const i = info(d);
              const etiqueta = etiquetas.get(d.protocol);
              return (
                <g
                  key={d.protocol}
                  className="cursor-default"
                  onMouseMove={(e) => onPasar(e, d)}
                  onMouseLeave={onSalir}
                >
                  <circle
                    cx={cx}
                    cy={cy}
                    r={r}
                    style={{
                      fill: `color-mix(in srgb, ${i.color} 22%, transparent)`,
                      stroke: i.color,
                    }}
                    strokeWidth={1.3}
                  />
                  <circle cx={cx} cy={cy} r={1.8} style={{ fill: i.color }} />
                  <text
                    x={etiqueta?.x ?? cx + r + 6}
                    y={etiqueta?.y ?? cy + 3.5}
                    textAnchor={etiqueta?.ancla ?? 'start'}
                    className="font-mono-display"
                    fontSize={11}
                    fill="rgb(var(--tinta) / 0.85)"
                  >
                    {i.name}
                  </text>
                </g>
              );
            })}
        </svg>
      )}
      {trazos.length > 0 && <ManoAlzada trazos={trazos} notas={notas} />}
    </div>
  );
}

export default function Protocols({ detail }: { detail: ProtocolDetail[] }) {
  const { t, lang } = useI18n();
  const tip = useTooltip();
  // el canal de datos pasivo es un efecto secundario de FTP, no una superficie de ataque propia
  const vectors = detail.filter((d) => d.protocol !== 'ftpdatalisten');
  const totalEvents = vectors.reduce((a, b) => a + b.count, 0);
  const maxEvents = Math.max(...vectors.map((d) => d.count), 1);
  const maxSources = Math.max(...vectors.map((d) => d.sources), 1);

  const info = (d: ProtocolDetail): Info =>
    (lang === 'en' ? PROTOCOL_INFO_EN : PROTOCOL_INFO)[d.protocol] ?? {
      name: d.protocol,
      what: t.protocols.unknown,
      why: '',
      color: 'var(--ghost-slate)',
    };

  /**
   * El contraste que hace al punto de la sección: dos servicios pueden recibir volúmenes parecidos
   * y significar cosas opuestas según cuántas máquinas distintas los golpeen.
   *
   * De un lado el que más eventos junta por dirección, del otro el que llega desde más direcciones.
   * Se eligen así y no fijando SMB y HTTP a mano: si el tráfico cambia de forma, la comparación
   * sigue mostrando el contraste real.
   */
  const porOrigen = (d: ProtocolDetail) => d.count / (d.sources || 1);
  const candidatos = vectors.filter((d) => d.sources > 5);
  const insistente = [...candidatos].sort((a, b) => porOrigen(b) - porOrigen(a))[0];
  const disperso = [...candidatos]
    .filter((d) => d !== insistente)
    .sort((a, b) => b.sources - a.sources)[0];
  const brecha =
    insistente && disperso && porOrigen(disperso) > 0
      ? porOrigen(insistente) / porOrigen(disperso)
      : 0;

  const detalle = (d: ProtocolDetail): ReactNode => (
    <div className="min-w-[190px]">
      <div className="text-[11px] text-white/90">{info(d).name}</div>
      <div className="cifra-chica text-white mt-0.5">{n(d.count)}</div>
      <div className="text-[10px] text-white/45">{t.protocols.tipEvents}</div>
      <div className="flex flex-col gap-1 mt-2 pt-2 border-t border-white/8 text-[10px] text-white/50">
        <span className="flex justify-between gap-4">
          {t.protocols.tipSources}
          <span className="font-data text-white/80">{n(d.sources)}</span>
        </span>
        <span className="flex justify-between gap-4">
          {t.protocols.tipPerSource}
          <span className="font-data text-white/80">{n(Math.round(porOrigen(d)))}</span>
        </span>
        <span className="flex justify-between gap-4">
          {t.protocols.tipShare}
          <span className="font-data text-white/80">{pct(d.count, totalEvents)}%</span>
        </span>
      </div>
    </div>
  );

  return (
    <section className="flex flex-col gap-4">
      <Tooltip content={tip.content} at={tip.at} />

      <Reveal>
        <div className="panel p-4">
          <div className="text-[11px] text-white/60 leading-relaxed">
            {t.protocols.intro1} <span className="text-white/85">{t.protocols.introStrong}</span>{' '}
            {t.protocols.intro2}
          </div>
        </div>
      </Reveal>

      <Reveal delay={60}>
        <div className="panel p-4">
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <span className="rotulo">{t.protocols.contrastTitle}</span>
            <span className="text-[10px]" style={{ color: 'rgba(212,134,10,0.65)' }}>
              {t.protocols.isoNote}
            </span>
          </div>
          <div className="grid lg:grid-cols-[minmax(0,1fr)_240px] gap-4 mt-3 items-center">
            <Dispersion
              vectores={vectors}
              info={info}
              insistente={insistente}
              disperso={disperso}
              mostrarContraste={brecha > 2}
              onPasar={(e, d) => tip.show(e, detalle(d))}
              onSalir={tip.hide}
            />
            {brecha > 2 && insistente && disperso && (
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-[1fr_auto_1fr] lg:grid-cols-1 gap-3 items-center">
                  {[insistente, disperso].map((d, i) => (
                    <div
                      key={d.protocol}
                      className={`rounded-lg bg-white/[0.03] p-3 ${i === 1 ? 'order-3 lg:order-none' : ''}`}
                    >
                      <div className="titulo text-[12px]" style={{ color: info(d).color }}>
                        {info(d).name}
                      </div>
                      <div className="cifra mt-1">{n(Math.round(porOrigen(d)))}</div>
                      <div className="text-[10px] text-white/40 mt-0.5">
                        {t.protocols.perSourceLabel}
                      </div>
                      <div className="font-data text-[10px] text-white/30 mt-1">
                        {t.protocols.fromSources(n(d.sources))}
                      </div>
                    </div>
                  ))}
                  <div className="order-2 lg:order-none text-center lg:text-left">
                    <span className="font-data text-lg" style={{ color: 'var(--agent-coral)' }}>
                      {t.protocols.times(n(Math.round(brecha)))}
                    </span>
                    <div className="rotulo mt-0.5">{t.protocols.gap}</div>
                  </div>
                </div>
              </div>
            )}
          </div>
          {brecha > 2 && (
            <div className="text-[11px] text-white/55 leading-relaxed mt-3">
              {t.protocols.contrastNote}
            </div>
          )}
        </div>
      </Reveal>

      <div className="bar-group grid md:grid-cols-2 gap-3">
        {vectors.map((d, i) => {
          const datos = info(d);
          return (
            <Reveal key={d.protocol} delay={Math.min(i * 60, 300)}>
              <div
                className="bar-item panel overflow-hidden p-4 h-full transition-opacity duration-200 cursor-default"
                onMouseMove={(e) => tip.show(e, detalle(d))}
                onMouseLeave={tip.hide}
              >
                <span
                  className="absolute inset-x-0 top-0 h-px"
                  style={{
                    background: `linear-gradient(90deg, transparent, ${datos.color}, transparent)`,
                  }}
                />
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-2.5">
                    <span className="w-2 h-2 rounded-sm" style={{ background: datos.color }} />
                    <span className="titulo">{datos.name}</span>
                    {d.port && (
                      <span className="font-data text-[10px] text-white/30">
                        {t.protocols.port} {d.port}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 font-data text-[10px]">
                    <span className="text-white/45">
                      <span className="text-white/80">{n(d.count)}</span> {t.protocols.events}
                    </span>
                    <span className="text-white/45">
                      <span className="text-white/80">{n(d.sources)}</span> {t.protocols.sources}
                    </span>
                  </div>
                </div>

                {/* Dos barras, volumen y alcance: juntas cuentan historias muy distintas. */}
                <div className="flex flex-col gap-1.5 mt-3">
                  {[
                    { rotulo: t.protocols.volume, valor: d.count / maxEvents, opacidad: 1 },
                    { rotulo: t.protocols.reach, valor: d.sources / maxSources, opacidad: 0.45 },
                  ].map((b) => (
                    <div key={b.rotulo} className="flex items-center gap-2">
                      <span className="rotulo w-16 shrink-0">{b.rotulo}</span>
                      <div className="flex-1 h-1.5 rounded bg-white/5 overflow-hidden">
                        <div
                          className="h-1.5 rounded transition-all duration-700"
                          style={{
                            width: `${b.valor * 100}%`,
                            background: datos.color,
                            opacity: b.opacidad,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

                <div className="text-[11px] text-white/60 mt-3 leading-relaxed">{datos.what}</div>
                {datos.why && (
                  <div className="text-[11px] text-white/45 mt-1 leading-relaxed">{datos.why}</div>
                )}
              </div>
            </Reveal>
          );
        })}
      </div>

      <Reveal delay={150}>
        <div className="panel p-4">
          <div className="rotulo mb-2">{t.protocols.lessonTitle}</div>
          <div className="text-[11px] text-white/55 leading-relaxed">{t.protocols.lesson}</div>
        </div>
      </Reveal>
    </section>
  );
}
