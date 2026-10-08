import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Download, FileDown, LoaderCircle } from 'lucide-react';
import { api, type ReporteGeneral } from '../../lib/api';
import { n } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { useSesion } from '../../lib/sesion';
import Hojas, { PARTES, rangoDelReporte, type Parte } from '../reporte/Hojas';
import { armarCsv, descargar } from '../reporte/csv';

type Preset = 'semana' | 'mes' | 'esteMes' | 'todo' | 'propio';
const PRESETS: Preset[] = ['semana', 'mes', 'esteMes', 'todo', 'propio'];

// El ancho de una hoja A4 en píxeles de pantalla: la vista previa la achica a lo que haya.
const ANCHO_A4 = 794;

const restarDias = (dia: string, dias: number) => {
  const d = new Date(`${dia}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - dias);
  return d.toISOString().slice(0, 10);
};

/** El día de hoy como AAAA-MM-DD en la zona de quien descarga, para el nombre del archivo. */
const hoy = () => new Date().toLocaleDateString('sv-SE');

/**
 * La reportería. Se elige un rango y qué hojas lleva el reporte; la vista previa las muestra tal
 * como van a salir, y cada conjunto de datos del rango se puede llevar suelto en CSV. La versión
 * impresa la arma el navegador, con el nombre "Reporte general" y la fecha del día.
 */
export default function Reportes({ primero, ultimo }: { primero: string; ultimo: string }) {
  const { t } = useI18n();
  const r = t.reportes;
  const sesion = useSesion();
  const [preset, setPreset] = useState<Preset>('todo');
  const [propio, setPropio] = useState({ desde: primero, hasta: ultimo });
  const [partes, setPartes] = useState<Parte[]>(PARTES);
  const [datos, setDatos] = useState<ReporteGeneral | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [escala, setEscala] = useState(0.6);
  const previa = useRef<HTMLDivElement>(null);

  // Los atajos cuentan hacia atrás desde el último evento capturado y no desde hoy: si la captura
  // se cortó, "los últimos 7 días" siguen teniendo datos.
  const [desde, hasta] = useMemo((): [string | undefined, string | undefined] => {
    const tope = (dia: string) => (dia < primero ? primero : dia);
    if (preset === 'semana') return [tope(restarDias(ultimo, 6)), ultimo];
    if (preset === 'mes') return [tope(restarDias(ultimo, 29)), ultimo];
    if (preset === 'esteMes') return [tope(`${ultimo.slice(0, 8)}01`), ultimo];
    if (preset === 'propio') return [propio.desde, propio.hasta];
    return [undefined, undefined];
  }, [preset, propio, primero, ultimo]);

  useEffect(() => {
    if (desde && hasta && desde > hasta) return;
    let vigente = true;
    setCargando(true);
    setError(null);
    const espera = window.setTimeout(() => {
      api
        .reporte(desde, hasta)
        .then((d) => vigente && setDatos(d))
        .catch((e) => vigente && setError(String(e.message ?? e)))
        .finally(() => vigente && setCargando(false));
    }, 250);
    return () => {
      vigente = false;
      window.clearTimeout(espera);
    };
  }, [desde, hasta]);

  useEffect(() => {
    const nodo = previa.current;
    if (!nodo) return;
    // se descuenta el relleno del contenedor, 18 px de cada lado
    const medir = () => setEscala(Math.min(1, (nodo.clientWidth - 36) / ANCHO_A4));
    medir();
    const observador = new ResizeObserver(medir);
    observador.observe(nodo);
    return () => observador.disconnect();
  }, []);

  // El título de la página es el nombre que el navegador le propone al archivo. Se cambia solo
  // mientras se imprime, y se devuelve cuando termina o cuando se sale de la sección.
  const tituloOriginal = useRef(document.title);
  useEffect(() => {
    const original = tituloOriginal.current;
    return () => {
      document.title = original;
      document.documentElement.classList.remove('con-reporte');
    };
  }, []);

  const generado = {
    fecha: new Date().toLocaleString(undefined, {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }),
    usuario: sesion.usuario,
    rol: t.roles[sesion.rol],
  };

  const [primerDia, ultimoDia] = datos ? rangoDelReporte(datos) : ['', ''];
  const tramo = `${primerDia}-al-${ultimoDia}`;

  const pdf = () => {
    if (!datos) return;
    api.avisarReporte({ formato: 'pdf', desde, hasta }).catch(() => undefined);
    const restaurar = () => {
      document.title = tituloOriginal.current;
      document.documentElement.classList.remove('con-reporte');
      window.removeEventListener('afterprint', restaurar);
    };
    window.addEventListener('afterprint', restaurar);
    document.title = `${r.archivo} ${hoy()}`;
    document.documentElement.classList.add('con-reporte');
    window.print();
  };

  const c = datos?.captura;
  const conjuntos = c
    ? [
        {
          id: 'dias',
          filas: c.por_dia.length,
          armar: () =>
            armarCsv(
              ['fecha', 'eventos', 'intentos de ingreso'],
              c.por_dia.map((d) => [d.date, d.count, d.logins]),
            ),
        },
        {
          id: 'horas',
          filas: 24,
          armar: () =>
            armarCsv(
              ['hora UTC', 'eventos'],
              c.por_hora.map((v, i) => [String(i).padStart(2, '0'), v]),
            ),
        },
        {
          id: 'protocolos',
          filas: c.protocolos.length,
          armar: () =>
            armarCsv(
              ['protocolo', 'eventos', 'direcciones distintas'],
              c.protocolos.map((p) => [p.protocol, p.count, p.sources]),
            ),
        },
        {
          id: 'paises',
          filas: c.paises.length,
          armar: () =>
            armarCsv(
              ['código', 'país', 'eventos', 'direcciones distintas'],
              c.paises.map((p) => [p.iso, p.country, p.count, p.sources]),
            ),
        },
        {
          id: 'redes',
          filas: c.sistemas.length,
          armar: () =>
            armarCsv(
              ['red', 'eventos', 'direcciones distintas'],
              c.sistemas.map((s) => [s.organization, s.count, s.sources]),
            ),
        },
        {
          id: 'usuarios',
          filas: c.usuarios.length,
          armar: () =>
            armarCsv(
              ['usuario', 'intentos'],
              c.usuarios.map((u) => [u.key, u.count]),
            ),
        },
        {
          id: 'contrasenas',
          filas: c.contrasenas.length,
          armar: () =>
            armarCsv(
              ['contraseña', 'intentos'],
              c.contrasenas.map((u) => [u.key, u.count]),
            ),
        },
        {
          id: 'comandos',
          filas: c.comandos.length,
          armar: () =>
            armarCsv(
              ['comando', 'veces'],
              c.comandos.map((u) => [u.key, u.count]),
            ),
        },
      ]
    : [];

  const bajarCsv = (id: string, armar: () => string) => {
    descargar(`honeyml-${id}-${tramo}.csv`, armar());
    api.avisarReporte({ formato: 'csv', conjunto: id, desde, hasta }).catch(() => undefined);
  };

  const alternar = (parte: Parte) =>
    setPartes((actuales) =>
      actuales.includes(parte)
        ? actuales.filter((p) => p !== parte)
        : PARTES.filter((p) => p === parte || actuales.includes(p)),
    );

  return (
    <div className="reportes">
      <aside className="reportes-mando">
        <section className="pliego">
          <h2 className="reportes-rotulo">{r.rango}</h2>
          <div className="flex flex-wrap gap-1.5">
            {PRESETS.map((p) => (
              <button
                key={p}
                onClick={() => setPreset(p)}
                aria-pressed={preset === p}
                className="filtro-auditoria"
              >
                {r.presets[p]}
              </button>
            ))}
          </div>
          {preset === 'propio' && (
            <div className="grid grid-cols-2 gap-2 mt-3">
              {(['desde', 'hasta'] as const).map((campo) => (
                <label key={campo} className="flex flex-col gap-1">
                  <span className="text-[11.5px] text-white/55">{r[campo]}</span>
                  <input
                    type="date"
                    min={primero}
                    max={ultimo}
                    value={propio[campo]}
                    onChange={(e) =>
                      e.target.value && setPropio((v) => ({ ...v, [campo]: e.target.value }))
                    }
                    className="campo-formulario"
                  />
                </label>
              ))}
            </div>
          )}

          <h2 className="reportes-rotulo mt-6">{r.contenido}</h2>
          <div className="flex flex-wrap gap-1.5">
            {PARTES.map((p) => (
              <button
                key={p}
                onClick={() => alternar(p)}
                aria-pressed={partes.includes(p)}
                className="filtro-auditoria"
              >
                {r.partes[p]}
              </button>
            ))}
          </div>

          <button
            onClick={pdf}
            disabled={!datos || cargando}
            className="boton-formulario w-full mt-6"
          >
            {cargando ? (
              <LoaderCircle className="w-4 h-4 animate-spin" />
            ) : (
              <FileDown className="w-4 h-4" />
            )}
            {cargando ? r.cargando : r.pdf}
          </button>
          <p className="text-[11.5px] leading-snug text-white/50 mt-2.5">{r.pdfAyuda}</p>
        </section>

        <section className="pliego mt-4">
          <h2 className="reportes-rotulo">{r.csv}</h2>
          <p className="text-[12px] text-white/50 -mt-1 mb-3">{r.csvAyuda}</p>
          <ul className="reportes-conjuntos">
            {conjuntos.map(({ id, filas, armar }) => (
              <li key={id}>
                <button onClick={() => bajarCsv(id, armar)} disabled={cargando}>
                  <span>{r.conjuntos[id]}</span>
                  <small>{r.filas(n(filas))}</small>
                  <Download className="w-3.5 h-3.5" aria-hidden />
                </button>
              </li>
            ))}
            <li>
              <a href={api.urlDecisionesCsv({ estado: 'todas', desde, hasta })} download>
                <span>{r.conjuntos.decisiones}</span>
                <small>{datos?.motor ? r.filas(n(Math.min(10_000, datos.motor.total))) : ''}</small>
                <Download className="w-3.5 h-3.5" aria-hidden />
              </a>
            </li>
            <li>
              <a href={api.urlRevisionesCsv()} download>
                <span>{r.conjuntos.veredictos}</span>
                <small />
                <Download className="w-3.5 h-3.5" aria-hidden />
              </a>
            </li>
          </ul>
        </section>
      </aside>

      <section className="reportes-previa" aria-busy={cargando}>
        <div className="flex items-center gap-3 mb-3">
          <h2 className="reportes-rotulo !mb-0">{r.vistaPrevia}</h2>
          <span className="text-[12px] text-white/45">{r.hojas(1 + partes.length)}</span>
          {cargando && <LoaderCircle className="w-4 h-4 animate-spin text-[var(--honey-amber)]" />}
        </div>
        {error && <p className="text-[13px] text-[var(--agent-coral)]">{error}</p>}
        <div
          ref={previa}
          className="previa-hojas"
          data-cargando={cargando ? 'si' : undefined}
          style={{ '--escala': escala } as React.CSSProperties}
        >
          {datos && <Hojas datos={datos} partes={partes} generado={generado} />}
        </div>
      </section>

      {datos &&
        createPortal(
          <div className="reporte-impresion">
            <Hojas datos={datos} partes={partes} generado={generado} />
          </div>,
          document.body,
        )}
    </div>
  );
}
