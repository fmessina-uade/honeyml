import type { ProtocolDetail } from '../../lib/api';
import Reveal from '../Reveal';
import Tooltip, { useTooltip } from '../Tooltip';
import { n, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';

/**
 * What each exposed service is, and why someone knocks on it. The point of the section is that
 * SSH is the door everyone remembers to lock and the others are the ones left open.
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
    color: '#a78bfa',
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
    color: '#60a5fa',
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
      color: '#a78bfa',
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
      color: '#60a5fa',
    },
    ftpdatalisten: {
      name: 'FTP (data channel)',
      what: 'The secondary connection FTP opens to transfer the file.',
      why: 'Not a vector of its own: it appears as a consequence of FTP activity. Shown so the totals add up.',
      color: 'rgba(148,163,184,0.5)',
    },
  };

export default function Protocols({ detail }: { detail: ProtocolDetail[] }) {
  const { t, lang } = useI18n();
  const tip = useTooltip();
  // the passive data channel is a side effect of FTP, not an attack surface of its own
  const vectors = detail.filter((d) => d.protocol !== 'ftpdatalisten');
  const totalEvents = vectors.reduce((a, b) => a + b.count, 0);
  const maxEvents = Math.max(...vectors.map((d) => d.count), 1);
  const maxSources = Math.max(...vectors.map((d) => d.sources), 1);

  /**
   * El contraste que hace al punto de la sección: dos servicios pueden recibir volúmenes parecidos
   * y significar cosas opuestas según cuántas máquinas distintas los golpeen.
   *
   * Se eligen por extremos de eventos por origen en lugar de fijar SMB y HTTP a mano: si mañana el
   * tráfico cambia de forma, la comparación sigue mostrando el contraste real y no uno histórico.
   */
  const porOrigen = (d: ProtocolDetail) => d.count / (d.sources || 1);
  const ordenados = [...vectors]
    .filter((d) => d.sources > 5)
    .sort((a, b) => porOrigen(b) - porOrigen(a));
  const insistente = ordenados[0];
  const disperso = ordenados[ordenados.length - 1];
  const brecha =
    insistente && disperso && porOrigen(disperso) > 0
      ? porOrigen(insistente) / porOrigen(disperso)
      : 0;

  return (
    <section className="flex flex-col gap-4">
      <Tooltip content={tip.content} at={tip.at} />

      <Reveal>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="text-[11px] text-white/60 leading-relaxed">
            {t.protocols.intro1} <span className="text-white/85">{t.protocols.introStrong}</span>{' '}
            {t.protocols.intro2}
          </div>
        </div>
      </Reveal>

      {/* El contraste, arriba de la lista: es la lectura que la lista sola no entrega. */}
      {brecha > 2 && (
        <Reveal delay={60}>
          <div className="tile rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
            <span className="tile-glow" style={{ background: 'var(--agent-coral)' }} />
            <div className="relative">
              <div className="text-[9px] uppercase tracking-wider text-white/35 mb-3">
                {t.protocols.contrastTitle}
              </div>
              <div className="grid sm:grid-cols-[1fr_auto_1fr] gap-3 items-center">
                {[insistente, disperso].map((d, i) => (
                  <div key={d.protocol} className={i === 1 ? 'sm:order-3' : ''}>
                    <div className="text-[11px] text-white/80">
                      {(lang === 'en' ? PROTOCOL_INFO_EN : PROTOCOL_INFO)[d.protocol]?.name ??
                        d.protocol}
                    </div>
                    <div className="font-data text-2xl text-white mt-1">
                      {n(Math.round(porOrigen(d)))}
                    </div>
                    <div className="text-[10px] text-white/40 mt-0.5">
                      {t.protocols.perSourceLabel}
                    </div>
                    <div className="font-data text-[10px] text-white/30 mt-1">
                      {n(d.count)} · {n(d.sources)} {t.protocols.sourcesShort}
                    </div>
                  </div>
                ))}
                <div className="sm:order-2 text-center">
                  <div className="font-data text-lg" style={{ color: 'var(--agent-coral)' }}>
                    {n(Math.round(brecha))}×
                  </div>
                  <div className="text-[9px] uppercase tracking-wider text-white/25">
                    {t.protocols.gap}
                  </div>
                </div>
              </div>
              <div className="text-[11px] text-white/55 leading-relaxed mt-3">
                {t.protocols.contrastNote}
              </div>
            </div>
          </div>
        </Reveal>
      )}

      <div className="bar-group grid gap-3">
        {vectors.map((d, i) => {
          const info = (lang === 'en' ? PROTOCOL_INFO_EN : PROTOCOL_INFO)[d.protocol] ?? {
            name: d.protocol,
            what: 'Servicio expuesto por el sensor multiprotocolo.',
            why: '',
            color: 'var(--ghost-slate)',
          };
          // events per source separates a worm retrying from a broad scan
          const perSource = d.sources ? d.count / d.sources : 0;

          return (
            <Reveal key={d.protocol} delay={i * 70}>
              <div
                className="bar-item rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4 transition-opacity duration-200 cursor-default"
                onMouseMove={(e) =>
                  tip.show(
                    e,
                    <div className="min-w-[190px]">
                      <div className="text-[11px] text-white/90">{info.name}</div>
                      <div className="font-data text-[15px] text-white mt-0.5">{n(d.count)}</div>
                      <div className="text-[10px] text-white/45">{t.protocols.tipEvents}</div>
                      <div className="flex flex-col gap-1 mt-2 pt-2 border-t border-white/8 text-[10px] text-white/50">
                        <span className="flex justify-between gap-4">
                          {t.protocols.tipSources}
                          <span className="font-data text-white/80">{n(d.sources)}</span>
                        </span>
                        <span className="flex justify-between gap-4">
                          {t.protocols.tipPerSource}
                          <span className="font-data text-white/80">
                            {perSource.toLocaleString('es-AR', { maximumFractionDigits: 0 })}
                          </span>
                        </span>
                        <span className="flex justify-between gap-4">
                          {t.protocols.tipShare}
                          <span className="font-data text-white/80">
                            {pct(d.count, totalEvents)}%
                          </span>
                        </span>
                      </div>
                    </div>,
                  )
                }
                onMouseLeave={tip.hide}
              >
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="flex items-center gap-2.5">
                    <span className="w-2 h-2 rounded-sm" style={{ background: info.color }} />
                    <span className="text-[13px] text-white/90 font-mono-display">{info.name}</span>
                    {d.port && (
                      <span className="font-data text-[10px] text-white/30">
                        {t.protocols.port} {d.port}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-5 font-data text-[10px]">
                    <span className="text-white/45">
                      <span className="text-white/80">{n(d.count)}</span> {t.protocols.events}
                    </span>
                    <span className="text-white/45">
                      <span className="text-white/80">{n(d.sources)}</span> {t.protocols.sources}
                    </span>
                  </div>
                </div>

                {/* two bars: volume and reach. They tell very different stories. */}
                <div className="flex flex-col gap-1 mt-3">
                  <div className="flex items-center gap-2">
                    <span className="text-[8px] uppercase tracking-wider text-white/25 w-16 shrink-0">
                      {t.protocols.volume}
                    </span>
                    <div className="flex-1 h-1.5 rounded bg-white/5 overflow-hidden">
                      <div
                        className="h-1.5 rounded transition-all duration-700"
                        style={{ width: `${(d.count / maxEvents) * 100}%`, background: info.color }}
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[8px] uppercase tracking-wider text-white/25 w-16 shrink-0">
                      {t.protocols.reach}
                    </span>
                    <div className="flex-1 h-1.5 rounded bg-white/5 overflow-hidden">
                      <div
                        className="h-1.5 rounded transition-all duration-700"
                        style={{
                          width: `${(d.sources / maxSources) * 100}%`,
                          background: info.color,
                          opacity: 0.45,
                        }}
                      />
                    </div>
                  </div>
                </div>

                <div className="text-[11px] text-white/60 mt-3 leading-relaxed">{info.what}</div>
                {info.why && (
                  <div className="text-[11px] text-white/45 mt-1 leading-relaxed">{info.why}</div>
                )}
              </div>
            </Reveal>
          );
        })}
      </div>

      <Reveal delay={150}>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="text-[9px] uppercase tracking-wider text-white/35 mb-2">
            {t.protocols.lessonTitle}
          </div>
          <div className="text-[11px] text-white/55 leading-relaxed">{t.protocols.lesson}</div>
        </div>
      </Reveal>
    </section>
  );
}
