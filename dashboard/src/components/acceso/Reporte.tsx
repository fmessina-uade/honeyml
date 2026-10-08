import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeft, FileDown, LoaderCircle } from 'lucide-react';
import { api, type Bucket, type ResumenTriaje, type Snapshot } from '../../lib/api';
import { compacto, dec, duracion, fechaHora, n, nombreDePais, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { useSesion } from '../../lib/sesion';
import { SEVERIDADES, colorDeSeveridad } from '../triaje/comunes';

/**
 * El reporte imprimible. Lo arma el navegador al imprimir, así sale con las letras y los colores del
 * panel sin generar nada en el servidor, y funciona igual desde el teléfono. La hoja va siempre en
 * el tema oscuro de la marca, elija lo que elija quien lo pide: es un documento, no una pantalla.
 *
 * Mientras está abierto, la impresión muestra solo la hoja. Lo que lleva sale de lo mismo que el
 * panel: el snapshot y el resumen del motor, sin ninguna dirección.
 */
export default function Reporte({
  snapshot,
  onCerrar,
}: {
  snapshot: Snapshot;
  onCerrar: () => void;
}) {
  const { t } = useI18n();
  const r = t.reporte;
  const sesion = useSesion();
  const [motor, setMotor] = useState<ResumenTriaje | null>(null);
  const [listo, setListo] = useState(false);

  useEffect(() => {
    document.documentElement.classList.add('con-reporte');
    api
      .triaje()
      .then(setMotor)
      .catch(() => setMotor(null))
      .finally(() => setListo(true));
    const alTeclear = (e: KeyboardEvent) => e.key === 'Escape' && onCerrar();
    document.addEventListener('keydown', alTeclear);
    return () => {
      document.documentElement.classList.remove('con-reporte');
      document.removeEventListener('keydown', alTeclear);
    };
  }, [onCerrar]);

  const imprimir = () => {
    api.avisarReporte().catch(() => undefined);
    window.print();
  };

  const o = snapshot.overview;
  const desde = o.first_event?.slice(0, 10) ?? '';
  const hasta = o.last_event?.slice(0, 10) ?? '';
  const paises = (snapshot.geography?.countries ?? []).slice(0, 8);
  const usuarios = snapshot.credentials.users
    .filter((u) => !/\d{1,3}\.\d{1,3}\.\d{1,3}/.test(u.key))
    .slice(0, 8);
  const porSeveridad: Bucket[] = motor
    ? SEVERIDADES.map((s) => ({
        key: s,
        count: motor.por_severidad.find((b) => b.key === s)?.count ?? 0,
      }))
    : [];
  const porTactica = (motor?.por_tactica ?? []).slice(0, 7);

  return createPortal(
    <div className="reporte-vista" role="dialog" aria-modal="true" aria-label={r.titulo}>
      <div className="reporte-barra">
        <button onClick={onCerrar} className="boton-formulario" data-tipo="suave">
          <ArrowLeft className="w-4 h-4" />
          {r.cerrar}
        </button>
        <p className="text-[12px] text-white/55 hidden md:block max-w-md">{r.ayuda}</p>
        <button onClick={imprimir} className="boton-formulario" disabled={!listo}>
          {listo ? (
            <FileDown className="w-4 h-4" />
          ) : (
            <LoaderCircle className="w-4 h-4 animate-spin" />
          )}
          {listo ? r.imprimir : r.preparando}
        </button>
      </div>

      <article className="reporte-hoja">
        <header className="reporte-cabecera">
          <div className="flex items-center gap-3">
            <img src="/logo.png" alt="" width={44} height={44} />
            <div>
              <div className="reporte-marca">HoneyML</div>
              <div className="reporte-sub">{t.brand.subtitle}</div>
            </div>
          </div>
          <div className="text-right">
            <h1 className="reporte-titulo">{r.titulo}</h1>
            <div className="reporte-sub">{r.periodo(desde, hasta)}</div>
          </div>
        </header>

        <section className="reporte-bloque">
          <h2 className="reporte-ceja">{r.captura}</h2>
          <div className="reporte-cifras">
            {(
              [
                [compacto(o.events), r.eventos, 'var(--honey-amber)'],
                [n(o.unique_ips), r.direcciones, 'var(--neural-teal)'],
                [n(o.logins_success), r.ingresos, 'var(--agent-coral)'],
                [n(o.commands), r.comandos, 'var(--ghost-slate)'],
              ] as const
            ).map(([valor, rotulo, color]) => (
              <div key={rotulo}>
                <div className="reporte-cifra" style={{ color }}>
                  {valor}
                </div>
                <div className="reporte-rotulo">{rotulo}</div>
              </div>
            ))}
          </div>
        </section>

        {motor && (
          <section className="reporte-bloque">
            <h2 className="reporte-ceja">{r.motor}</h2>
            <div className="reporte-cifras">
              {(
                [
                  [n(motor.total), r.decisiones],
                  [pct(motor.copiadas, motor.total, 1), r.copiadas],
                  [
                    motor.conclusion.mediana_s != null ? duracion(motor.conclusion.mediana_s) : '—',
                    r.conclusion,
                  ],
                  [n(motor.revision.pendientes), r.pendientes],
                  [dec(motor.costo_usd, 2), r.costo],
                ] as const
              ).map(([valor, rotulo]) => (
                <div key={rotulo}>
                  <div className="reporte-cifra reporte-cifra-chica">{valor}</div>
                  <div className="reporte-rotulo">{rotulo}</div>
                </div>
              ))}
            </div>
            <div className="reporte-dos">
              <Barras
                titulo={r.severidades}
                filas={porSeveridad}
                nombre={(k) => t.severities[k as keyof typeof t.severities] ?? k}
                color={colorDeSeveridad}
              />
              <Barras
                titulo={r.tacticas}
                filas={porTactica}
                nombre={(k) =>
                  t.tactics[k as keyof typeof t.tactics]?.name ??
                  (k === 'ninguna' ? t.triage.noTactic : k)
                }
                color={() => 'var(--neural-teal)'}
              />
            </div>
          </section>
        )}

        <section className="reporte-bloque reporte-dos">
          <Barras
            titulo={r.paises}
            filas={paises.map((p) => ({ key: nombreDePais(p.iso, p.country), count: p.count }))}
            nombre={(k) => k}
            color={() => 'var(--honey-amber)'}
          />
          <Barras
            titulo={r.credenciales}
            filas={usuarios}
            nombre={(k) => k}
            color={() => 'var(--agent-coral)'}
            mono
          />
        </section>

        <footer className="reporte-pie">
          <span>{r.pie}</span>
          <span>{r.generado(fechaHora(new Date().toISOString()), sesion.usuario)}</span>
        </footer>
      </article>
    </div>,
    document.body,
  );
}

function Barras({
  titulo,
  filas,
  nombre,
  color,
  mono = false,
}: {
  titulo: string;
  filas: Bucket[];
  nombre: (key: string) => string;
  color: (key: string) => string;
  mono?: boolean;
}) {
  const maximo = Math.max(1, ...filas.map((f) => f.count));
  return (
    <div>
      <h3 className="reporte-subtitulo">{titulo}</h3>
      <ul className="reporte-barras">
        {filas.map((f) => (
          <li key={f.key}>
            <span className={mono ? 'reporte-nombre font-data' : 'reporte-nombre'}>
              {nombre(f.key)}
            </span>
            <span className="reporte-pista">
              <span style={{ width: `${(f.count / maximo) * 100}%`, background: color(f.key) }} />
            </span>
            <span className="reporte-valor">{n(f.count)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
