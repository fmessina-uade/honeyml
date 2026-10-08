import { useEffect, useRef, useState } from 'react';
import { Pause, Play } from 'lucide-react';
import { api, type EventoEnVivo } from '../../lib/api';
import { hora, n, nombreDePais } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { useQuieto } from '../../lib/useQuieto';

const SONDEO_MS = 3000;
const TOPE = 120;

/**
 * La telemetría a medida que llega, como una terminal que no para. Pide cada tres segundos solo lo
 * posterior al último evento que tiene, así cada pedido es chico aunque el corpus sea enorme. En
 * pausa deja de dibujar pero no de pedir: al seguir aparece todo lo que llegó en el medio.
 */
export default function EnVivo() {
  const { t } = useI18n();
  const v = t.envivo;
  const quieto = useQuieto();
  const [eventos, setEventos] = useState<EventoEnVivo[]>([]);
  const [nuevos, setNuevos] = useState<Set<string>>(new Set());
  const [pausa, setPausa] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ultimo = useRef<string | undefined>();
  const retenidos = useRef<EventoEnVivo[]>([]);
  const pausaRef = useRef(pausa);
  pausaRef.current = pausa;

  useEffect(() => {
    let vivo = true;
    const traer = () => {
      if (document.hidden) return;
      api
        .enVivo(ultimo.current)
        .then(({ eventos: llegados }) => {
          if (!vivo || llegados.length === 0) return;
          ultimo.current = llegados[0]['@timestamp'];
          retenidos.current = [...llegados, ...retenidos.current].slice(0, TOPE);
          if (!pausaRef.current) volcar();
          setError(null);
        })
        .catch((e) => vivo && setError(String(e.message ?? e)));
    };
    traer();
    const id = window.setInterval(traer, SONDEO_MS);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, []);

  const volcar = () => {
    const llegados = retenidos.current;
    retenidos.current = [];
    if (llegados.length === 0) return;
    setEventos((previos) => {
      const vistos = new Set(previos.map((e) => e.id));
      const sumados = llegados.filter((e) => !vistos.has(e.id));
      setNuevos(new Set(previos.length ? sumados.map((e) => e.id) : []));
      return [...sumados, ...previos].slice(0, TOPE);
    });
  };

  useEffect(() => {
    if (!pausa) volcar();
  }, [pausa]);

  const haceUnMinuto = Date.now() - 60_000;
  const porMinuto = eventos.filter(
    (e) => new Date(e['@timestamp']).getTime() > haceUnMinuto,
  ).length;

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center gap-4 flex-wrap">
        <button onClick={() => setPausa((p) => !p)} className="boton-formulario" data-tipo="suave">
          {pausa ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
          {pausa ? v.seguir : v.pausar}
        </button>
        <span className="flex items-baseline gap-2">
          <span className="cifra text-[22px] text-[var(--agent-coral)]">{n(porMinuto)}</span>
          <span className="text-[12.5px] text-white/55">{v.porMinuto}</span>
        </span>
        <span className="text-[12px] text-white/45">{v.ultimos(eventos.length)}</span>
        {error && <span className="text-[12.5px] text-[var(--agent-coral)]">{error}</span>}
      </div>

      <div className="consola-en-vivo" data-pausa={pausa ? 'si' : undefined} aria-live="off">
        {pausa && <p className="consola-aviso">{v.pausado}</p>}
        {eventos.length === 0 && <p className="consola-aviso">{v.esperando}</p>}
        <ol>
          {eventos.map((e) => (
            <li key={e.id} data-nuevo={!quieto && nuevos.has(e.id) ? 'si' : undefined}>
              <time>{hora(e['@timestamp'])}</time>
              <span className="consola-sensor" data-sensor={e.honeypot}>
                {e.honeypot ?? '?'}
              </span>
              <span className="consola-accion" data-resultado={e['event.outcome']}>
                {e['event.action'] ?? ''}
                {e['network.protocol'] && (
                  <span className="text-white/45"> {e['network.protocol']}</span>
                )}
                {e['destination.port'] != null && (
                  <span className="text-white/35">:{e['destination.port']}</span>
                )}
              </span>
              <span className="consola-detalle">
                {e['user.name'] && (
                  <span className="text-[var(--honey-amber)]">{e['user.name']} </span>
                )}
                {e['process.command_line'] ?? e['url.original'] ?? e['file.name'] ?? ''}
              </span>
              <span className="consola-origen">
                {e['source.geo.country_iso_code']
                  ? nombreDePais(
                      e['source.geo.country_iso_code'],
                      e['source.geo.country_name'] ?? '',
                    )
                  : v.sinOrigen}
                {e['source.as.organization.name'] && (
                  <span className="text-white/35"> {e['source.as.organization.name']}</span>
                )}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
