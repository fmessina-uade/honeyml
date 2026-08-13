import type { ProtocolDetail } from '../../lib/api';
import Reveal from '../Reveal';
import Tooltip, { useTooltip } from '../Tooltip';
import { n, pct } from '../../lib/format';

/**
 * What each exposed service is, and why someone knocks on it. The point of the section is that
 * SSH is the door everyone remembers to lock and the others are the ones left open.
 */
const PROTOCOL_INFO: Record<
  string,
  { name: string; what: string; why: string; color: string }
> = {
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

export default function Protocols({ detail }: { detail: ProtocolDetail[] }) {
  const tip = useTooltip();
  // the passive data channel is a side effect of FTP, not an attack surface of its own
  const vectors = detail.filter((d) => d.protocol !== 'ftpdatalisten');
  const totalEvents = vectors.reduce((a, b) => a + b.count, 0);
  const maxEvents = Math.max(...vectors.map((d) => d.count), 1);
  const maxSources = Math.max(...vectors.map((d) => d.sources), 1);

  return (
    <section className="flex flex-col gap-4">
      <Tooltip content={tip.content} at={tip.at} />

      <Reveal>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="text-[11px] text-white/60 leading-relaxed max-w-3xl">
            El señuelo no expone solo SSH. Estos son los otros servicios que dejó abiertos, y lo que
            llegó a cada uno. <span className="text-white/85">Nadie publicó esta dirección:</span>{' '}
            todo lo que ves lo encontró un escáner recorriendo internet.
          </div>
        </div>
      </Reveal>

      <div className="bar-group grid gap-3">
        {vectors.map((d, i) => {
          const info = PROTOCOL_INFO[d.protocol] ?? {
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
                      <div className="text-[10px] text-white/45">eventos capturados</div>
                      <div className="flex flex-col gap-1 mt-2 pt-2 border-t border-white/8 text-[10px] text-white/50">
                        <span className="flex justify-between gap-4">
                          direcciones distintas
                          <span className="font-data text-white/80">{n(d.sources)}</span>
                        </span>
                        <span className="flex justify-between gap-4">
                          eventos por dirección
                          <span className="font-data text-white/80">
                            {perSource.toLocaleString('es-AR', { maximumFractionDigits: 0 })}
                          </span>
                        </span>
                        <span className="flex justify-between gap-4">
                          del tráfico multiprotocolo
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
                      <span className="font-data text-[10px] text-white/30">puerto {d.port}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-5 font-data text-[10px]">
                    <span className="text-white/45">
                      <span className="text-white/80">{n(d.count)}</span> eventos
                    </span>
                    <span className="text-white/45">
                      <span className="text-white/80">{n(d.sources)}</span> direcciones
                    </span>
                  </div>
                </div>

                {/* two bars: volume and reach. They tell very different stories. */}
                <div className="flex flex-col gap-1 mt-3">
                  <div className="flex items-center gap-2">
                    <span className="text-[8px] uppercase tracking-wider text-white/25 w-16 shrink-0">
                      volumen
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
                      alcance
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
            Lo que enseña la comparación
          </div>
          <div className="text-[11px] text-white/55 leading-relaxed max-w-3xl">
            Mirá las dos barras de SMB y las de HTTP. SMB acumula el grueso del volumen desde muy
            pocas direcciones: es un puñado de gusanos reintentando sin parar contra el mismo puerto.
            HTTP es al revés, mucho menos tráfico repartido entre muchísimas más direcciones: son
            escáneres distintos barriendo internet una vez cada uno. El mismo número de eventos
            significa cosas opuestas según cuántos lo produjeron, y por eso contar alertas no alcanza
            para priorizarlas.
          </div>
        </div>
      </Reveal>
    </section>
  );
}
