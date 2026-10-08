import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Server, UserRound } from 'lucide-react';
import {
  api,
  type Auditoria as DatosDeAuditoria,
  type EntradaDeAuditoria,
  type RegistrosDelServidor,
} from '../../lib/api';
import { fechaHora, n } from '../../lib/format';
import { useI18n } from '../../lib/i18n';

// El color de cada acción dice qué mirar primero: lo que puede ser un ataque al panel en coral, lo
// que cambia cuentas en teal, el trabajo del analista en ámbar, y el resto en pizarra.
const TONO: Record<string, string> = {
  ingreso_fallido: 'var(--agent-coral)',
  ingreso_trabado: 'var(--agent-coral)',
  cuenta_creada: 'var(--neural-teal)',
  cuenta_modificada: 'var(--neural-teal)',
  contrasena_cambiada: 'var(--neural-teal)',
  veredicto: 'var(--honey-amber)',
  revision_a_ciegas: 'var(--honey-amber)',
  exportacion: 'var(--violeta)',
};

const TONO_FUENTE: Record<string, string> = {
  despliegues: 'var(--neural-teal)',
  vigilante: 'var(--agent-coral)',
  salud: 'var(--ghost-slate)',
  respaldo: 'var(--honey-amber)',
};

/**
 * La auditoría del superadmin, en dos pestañas. "En el panel" es lo que hizo cada cuenta, leído del
 * índice de auditoría; "En el servidor" son los registros que escribe el anfitrión por su cuenta:
 * despliegues, el vigilante de los sensores, el chequeo de salud y el respaldo.
 */
export default function Auditoria() {
  const { t } = useI18n();
  const [pestana, setPestana] = useState<'panel' | 'servidor'>('panel');

  return (
    <div className="flex flex-col gap-6">
      <div className="pestanas" role="tablist">
        {(
          [
            ['panel', t.auditoria.panel, UserRound],
            ['servidor', t.auditoria.servidor, Server],
          ] as const
        ).map(([id, rotulo, Icono]) => (
          <button
            key={id}
            role="tab"
            aria-selected={pestana === id}
            onClick={() => setPestana(id)}
            className="pestana"
          >
            <Icono className="w-4 h-4" aria-hidden />
            {rotulo}
          </button>
        ))}
      </div>
      {pestana === 'panel' ? <DelPanel /> : <DelServidor />}
    </div>
  );
}

function DelPanel() {
  const { t } = useI18n();
  const a = t.auditoria;
  const [accion, setAccion] = useState<string | undefined>();
  const [datos, setDatos] = useState<DatosDeAuditoria | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(
    (desde: number) => {
      api
        .auditoria(desde, accion)
        .then((r) =>
          setDatos((previos) =>
            desde > 0 && previos ? { ...r, items: [...previos.items, ...r.items] } : r,
          ),
        )
        .catch((e) => setError(String(e.message ?? e)));
    },
    [accion],
  );
  useEffect(() => cargar(0), [cargar]);

  const acciones = Object.entries(datos?.acciones ?? {}).sort((x, y) => y[1] - x[1]);

  return (
    <section className="pliego">
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => setAccion(undefined)}
          aria-pressed={!accion}
          className="filtro-auditoria"
        >
          {a.todas}
        </button>
        {acciones.map(([clave, cuantas]) => (
          <button
            key={clave}
            onClick={() => setAccion(clave)}
            aria-pressed={accion === clave}
            className="filtro-auditoria"
            style={{ '--tono': TONO[clave] ?? 'var(--ghost-slate)' } as React.CSSProperties}
          >
            {a.acciones[clave] ?? clave}
            <span className="cifra-chica text-white/50">{n(cuantas)}</span>
          </button>
        ))}
      </div>

      {error && <p className="text-[13px] text-[var(--agent-coral)] mt-4">{error}</p>}
      {datos && datos.items.length === 0 && (
        <p className="text-[13px] text-white/55 mt-6">{a.vacio}</p>
      )}

      <ol className="linea-auditoria mt-5">
        {datos?.items.map((e, i) => (
          <Entrada key={`${e['@timestamp']}-${i}`} e={e} />
        ))}
      </ol>

      {datos && datos.items.length < datos.total && (
        <button
          onClick={() => cargar(datos.items.length)}
          className="boton-formulario mt-5"
          data-tipo="suave"
        >
          {a.mas}
        </button>
      )}
    </section>
  );
}

function Entrada({ e }: { e: EntradaDeAuditoria }) {
  const { t } = useI18n();
  const a = t.auditoria;
  const tono = TONO[e.accion] ?? 'var(--ghost-slate)';
  const detalle = Object.entries(e.detalle ?? {})
    .map(([k, v]) =>
      typeof v === 'object' && v !== null
        ? `${k}: ${Object.values(v as Record<string, unknown>).join(' a ')}`
        : `${k}: ${String(v)}`,
    )
    .join(', ');
  return (
    <li className="entrada-auditoria" style={{ '--tono': tono } as React.CSSProperties}>
      <time className="font-data text-[11.5px] text-white/45 tabular-nums">
        {fechaHora(e['@timestamp'])}
      </time>
      <span className="geist text-[14px] text-white">
        <span style={{ color: tono }}>{a.acciones[e.accion] ?? e.accion}</span>
        {e.objetivo && <span className="text-white/60"> {e.objetivo}</span>}
      </span>
      <span className="text-[12.5px] text-white/60">
        {e.usuario === 'consola' ? a.consola : e.usuario}
        {e.rol && (
          <span className="rol-cuenta ml-2" data-rol={e.rol}>
            {t.roles[e.rol]}
          </span>
        )}
      </span>
      {detalle && (
        <span className="font-data text-[11.5px] text-white/45 break-all">{detalle}</span>
      )}
    </li>
  );
}

function DelServidor() {
  const { t } = useI18n();
  const a = t.auditoria;
  const [datos, setDatos] = useState<RegistrosDelServidor | null>(null);
  const [fuente, setFuente] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .registrosDelServidor()
      .then(setDatos)
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  if (error) return <p className="text-[13px] text-[var(--agent-coral)]">{error}</p>;
  if (!datos) return null;
  if (!datos.disponible) return <p className="pliego text-[13px] text-white/60">{a.sinMontaje}</p>;

  const entradas = datos.entradas.filter((e) => !fuente || e.fuente === fuente);

  return (
    <section className="pliego">
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => setFuente(undefined)}
          aria-pressed={!fuente}
          className="filtro-auditoria"
        >
          {a.todas}
        </button>
        {Object.entries(datos.fuentes).map(([clave, hay]) => (
          <button
            key={clave}
            onClick={() => setFuente(clave)}
            aria-pressed={fuente === clave}
            disabled={!hay}
            className="filtro-auditoria"
            style={{ '--tono': TONO_FUENTE[clave] } as React.CSSProperties}
          >
            {a.fuentes[clave] ?? clave}
            {!hay && <span className="text-white/40">{a.sinArchivo}</span>}
          </button>
        ))}
      </div>
      <ol className="registro-servidor mt-5">
        {entradas.map((e, i) => (
          <li
            key={i}
            data-alerta={e.alerta ? 'si' : undefined}
            style={{ '--tono': TONO_FUENTE[e.fuente] } as React.CSSProperties}
          >
            <time className="tabular-nums">{e.momento ? fechaHora(e.momento) : ''}</time>
            <span className="registro-fuente">{a.fuentes[e.fuente] ?? e.fuente}</span>
            <span className="registro-texto">
              {e.alerta && (
                <AlertTriangle
                  className="inline w-3.5 h-3.5 mr-1.5 -mt-0.5"
                  aria-label={a.alerta}
                />
              )}
              {e.texto}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
