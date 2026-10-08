import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  CircleHelp,
  Coins,
  Download,
  EyeOff,
  Inbox,
  PencilLine,
  Timer,
  Workflow,
} from 'lucide-react';
import {
  api,
  type DetalleDecision,
  type FilaDecision,
  type FiltrosDecisiones,
  type ListadoDecisiones,
} from '../../lib/api';
import { dec, duracion, fechaHora, n } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { useMotorEnVivo } from '../../lib/useMotorEnVivo';
import { useSesion } from '../../lib/sesion';
import Reveal from '../Reveal';
import EngineLive from '../EngineLive';
import { Indicador } from '../Instrumento';
import { Cajon } from '../Superpuesto';
import { tacticColor } from './SessionReplay';
import Guia from '../triaje/Guia';
import Detalle from '../triaje/Detalle';
import ModalVeredicto from '../triaje/ModalVeredicto';
import RevisionACiegas from '../triaje/RevisionACiegas';
import { ChipSeveridad, SIN_TACTICA, caminoDe, colorDeSeveridad } from '../triaje/comunes';

const TAMANO = 25;
const FILTROS_INICIALES: FiltrosDecisiones = { estado: 'todas', desde: 0, tamano: TAMANO };
const CLAVE_GUIA = 'honeyml-panel-guia-triaje';

function guiaCerrada(): boolean {
  try {
    return localStorage.getItem(CLAVE_GUIA) === 'cerrada';
  } catch {
    return false;
  }
}

/**
 * Lo que decidió el motor de triaje, y el lugar donde el analista tiene la última palabra.
 *
 * Está ordenado de lo general a lo particular y de lo que se mira a lo que se hace: el motor
 * trabajando, sus números, la bandeja de decisiones y, al elegir una, su detalle en un panel
 * lateral. El veredicto es un diálogo aparte, en dos pasos, porque es la única acción del panel
 * que escribe algo y conviene que no se confunda con mirar.
 *
 * Todo se alimenta de un mismo sondeo: cuando el motor decide algo, el grafo lo recorre, los
 * números cambian y la decisión aparece arriba en la bandeja, al mismo tiempo.
 */
export default function Triage() {
  const { t } = useI18n();
  const { resumen, recientes, llegada, error, recargarResumen } = useMotorEnVivo();
  // El invitado mira y exporta: la revisión a ciegas y el veredicto quedan para el analista.
  const escribe = useSesion().puede('analista');
  const [filtros, setFiltros] = useState<FiltrosDecisiones>(FILTROS_INICIALES);
  const [listado, setListado] = useState<ListadoDecisiones | null>(null);
  const [elegida, setElegida] = useState<string | null>(null);
  const [detalle, setDetalle] = useState<DetalleDecision | null>(null);
  const [errorDetalle, setErrorDetalle] = useState<string | null>(null);
  const [revisando, setRevisando] = useState(false);
  const [aCiegas, setACiegas] = useState(false);
  const [guia, setGuia] = useState(() => !guiaCerrada());
  const [nuevas, setNuevas] = useState<Set<string>>(new Set());
  const bandeja = useRef<HTMLDivElement>(null);
  // La primera página se recarga cuando el motor trae algo nuevo; la referencia evita que el efecto
  // de las llegadas dependa de los filtros y recargue también cuando lo que cambió fue un filtro.
  const cargarListadoRef = useRef<() => void>(() => undefined);
  const primeraPagina = useRef(true);

  const tacticName = (key: string) =>
    key === SIN_TACTICA
      ? t.triage.noTactic
      : (t.tactics[key as keyof typeof t.tactics]?.name ?? key);

  const cargarListado = useCallback(() => {
    api
      .decisiones(filtros)
      .then(setListado)
      .catch(() => setListado({ total: 0, items: [] }));
  }, [filtros]);
  cargarListadoRef.current = cargarListado;
  primeraPagina.current = filtros.desde === 0;

  useEffect(cargarListado, [cargarListado]);

  // Lo que llega del motor entra a la bandeja en el acto, si se está mirando la primera página, y
  // se marca un momento para que se note qué es nuevo.
  useEffect(() => {
    if (llegada.serie === 0) return;
    if (primeraPagina.current) cargarListadoRef.current();
    setNuevas(new Set(llegada.filas.map((d) => d.doc_id)));
    const id = window.setTimeout(() => setNuevas(new Set()), 4000);
    return () => window.clearTimeout(id);
  }, [llegada]);

  const cargarDetalle = useCallback((docId: string) => {
    setErrorDetalle(null);
    api
      .decision(docId)
      .then(setDetalle)
      .catch((e) => setErrorDetalle(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    setDetalle(null);
    if (elegida) cargarDetalle(elegida);
  }, [elegida, cargarDetalle]);

  const filtrar = (cambio: Partial<FiltrosDecisiones>) =>
    setFiltros((f) => ({ ...f, ...cambio, desde: 0 }));

  const cerrarGuia = () => {
    setGuia(false);
    try {
      localStorage.setItem(CLAVE_GUIA, 'cerrada');
    } catch {
      // sin almacenamiento, la guía vuelve a aparecer la próxima vez
    }
  };

  const irAPendientes = () => {
    filtrar({ estado: 'pendientes' });
    bandeja.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  if (error && !resumen) {
    return (
      <div className="panel p-4 flex gap-3">
        <AlertCircle className="w-4 h-4 text-[var(--agent-coral)] shrink-0 mt-0.5" />
        <div>
          <div className="text-[13px] text-white/85">{t.triage.liveOnly}</div>
          <div className="font-data text-[11px] text-white/45 mt-1">{error}</div>
        </div>
      </div>
    );
  }

  if (!resumen) {
    return (
      <div className="flex flex-col gap-3 animate-pulse">
        <div className="h-[420px] panel" />
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-[104px] panel" />
          ))}
        </div>
      </div>
    );
  }

  const pendientes = resumen.revision.pendientes;

  return (
    <section className="flex flex-col gap-4">
      {guia ? (
        <Guia onCerrar={cerrarGuia} />
      ) : (
        <button
          onClick={() => setGuia(true)}
          className="self-start flex items-center gap-1.5 text-[11px] text-white/45 hover:text-white/80 transition -mb-1"
        >
          <CircleHelp className="w-3.5 h-3.5" />
          {t.triage.guide.show}
        </button>
      )}

      {/* El motor trabajando, que es lo primero que hay que ver */}
      <EngineLive
        resumen={resumen}
        recientes={recientes}
        llegada={llegada}
        error={error}
        tacticName={tacticName}
        onElegir={setElegida}
      />

      {/* Los cuatro números del motor */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Reveal>
          <Indicador
            icono={Workflow}
            rotulo={t.triage.decisions}
            valor={n(resumen.total)}
            sub={`${n(resumen.razonadas)} ${t.triage.reasoned}, ${n(resumen.copiadas)} ${t.triage.copied}`}
            color="var(--agent-coral)"
          />
        </Reveal>
        <Reveal delay={60}>
          <Indicador
            icono={Coins}
            rotulo={t.triage.cost}
            valor={`USD ${dec(resumen.costo_usd, 2)}`}
            sub={`${n(resumen.corregidas_por_el_motor)} ${t.triage.correctedByEngine}`}
            color="var(--honey-amber)"
          />
        </Reveal>
        <Reveal delay={120}>
          <Indicador
            icono={Timer}
            rotulo={t.triage.conclusion}
            valor={
              resumen.conclusion.mediana_s !== null ? (
                <span className="flex items-baseline gap-2.5 flex-wrap">
                  {duracion(resumen.conclusion.mediana_s)}
                  <span className="prosa text-[10px] text-white/40">{t.triage.median}</span>
                </span>
              ) : (
                <span className="prosa text-[13px] text-white/40">{t.triage.noData}</span>
              )
            }
            sub={
              resumen.conclusion.p90_s !== null
                ? t.triage.conclusionP90(
                    duracion(resumen.conclusion.p90_s),
                    resumen.conclusion.ventana_dias,
                    resumen.conclusion.media_s != null
                      ? duracion(resumen.conclusion.media_s)
                      : null,
                  )
                : t.triage.conclusionNote(resumen.conclusion.ventana_dias)
            }
            color="var(--neural-teal)"
          />
        </Reveal>
        <Reveal delay={180}>
          <Indicador
            icono={Inbox}
            rotulo={t.triage.pending}
            valor={n(pendientes)}
            sub={
              pendientes
                ? t.triage.pendingNote(n(resumen.revision.requieren))
                : t.triage.pendingNone(n(resumen.revision.revisadas))
            }
            color={pendientes ? 'var(--agent-coral)' : 'var(--ghost-slate)'}
            resaltado={pendientes > 0}
            onClick={irAPendientes}
          />
        </Reveal>
      </div>

      {/* La bandeja: las decisiones, con los filtros a la vista */}
      <div ref={bandeja} className="panel overflow-hidden scroll-mt-4">
        <div className="px-4 pt-4 pb-3 flex flex-col gap-3 border-b border-white/5">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2.5">
              <span className="titulo">{t.triage.inbox}</span>
              <span className="flex items-center gap-1.5 text-[10px] text-white/45">
                <span className="relative flex w-1.5 h-1.5">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--neural-teal)] opacity-60 animate-ping" />
                  <span className="relative inline-flex w-1.5 h-1.5 rounded-full bg-[var(--neural-teal)]" />
                </span>
                {t.triage.live}
              </span>
              {nuevas.size > 0 && (
                <span className="motor-aparece text-[10px] rounded-full px-2 py-0.5 bg-[var(--honey-amber)]/15 text-[var(--honey-amber)] ring-1 ring-[var(--honey-amber)]/35">
                  {t.triage.newOnes(nuevas.size)}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <a
                href={api.urlDecisionesCsv(filtros)}
                download
                title={t.exportar.decisionesAyuda}
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] text-white/70 ring-1 ring-white/15 hover:text-white hover:bg-white/[0.05] transition"
              >
                <Download className="w-3.5 h-3.5" />
                {t.exportar.decisiones}
              </a>
              <a
                href={api.urlRevisionesCsv()}
                download
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] text-white/70 ring-1 ring-white/15 hover:text-white hover:bg-white/[0.05] transition"
              >
                <Download className="w-3.5 h-3.5" />
                {t.exportar.revisiones}
              </a>
              {escribe && (
                <button
                  onClick={() => setACiegas(true)}
                  className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] text-[var(--honey-amber)] ring-1 ring-[var(--honey-amber)]/35 hover:bg-[var(--honey-amber)]/10 transition"
                >
                  <EyeOff className="w-3.5 h-3.5" />
                  {t.triage.blind.open}
                </button>
              )}
              <div
                role="tablist"
                className="flex rounded-lg ring-1 ring-white/10 bg-white/[0.03] p-0.5"
              >
                {(
                  [
                    ['pendientes', pendientes],
                    ['todas', resumen.total],
                    ['revisadas', resumen.revision.revisadas],
                  ] as const
                ).map(([estado, cuantas]) => (
                  <button
                    key={estado}
                    role="tab"
                    aria-selected={filtros.estado === estado}
                    onClick={() => filtrar({ estado })}
                    className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] transition ${
                      filtros.estado === estado
                        ? 'bg-white/10 text-white/90'
                        : 'text-white/50 hover:text-white/80'
                    }`}
                  >
                    {t.triage.state[estado]}
                    <span className="font-data text-[10px] text-white/40">{n(cuantas)}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 flex-wrap">
            {resumen.por_severidad.map((b) => {
              const activa = filtros.severidad === b.key;
              const color = colorDeSeveridad(b.key);
              return (
                <button
                  key={b.key}
                  onClick={() => filtrar({ severidad: activa ? undefined : b.key })}
                  aria-pressed={activa}
                  className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] transition"
                  style={{
                    color: activa ? color : 'rgb(var(--tinta) / 0.65)',
                    background: activa
                      ? `color-mix(in srgb, ${color} 14%, transparent)`
                      : 'rgb(var(--tinta) / 0.03)',
                    boxShadow: `inset 0 0 0 1px ${activa ? color : 'rgb(var(--tinta) / 0.1)'}`,
                  }}
                >
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
                  <span className="first-letter:uppercase">
                    {t.severities[b.key as keyof typeof t.severities] ?? b.key}
                  </span>
                  <span className="font-data text-[10px] opacity-60">{n(b.count)}</span>
                </button>
              );
            })}
            <select
              value={filtros.tactica ?? ''}
              onChange={(e) => filtrar({ tactica: e.target.value || undefined })}
              aria-label={t.triage.tactic}
              className="rounded-full bg-white/[0.03] ring-1 ring-white/10 px-2.5 py-1 text-[11px] text-white/70 outline-none"
            >
              <option value="">{t.triage.allTactics}</option>
              {resumen.por_tactica.map((b) => (
                <option key={b.key} value={b.key}>
                  {tacticName(b.key)} ({n(b.count)})
                </option>
              ))}
            </select>
            <select
              value={filtros.sensor ?? ''}
              onChange={(e) => filtrar({ sensor: e.target.value || undefined })}
              aria-label={t.triage.sensor}
              className="rounded-full bg-white/[0.03] ring-1 ring-white/10 px-2.5 py-1 text-[11px] text-white/70 outline-none"
            >
              <option value="">{t.triage.allSensors}</option>
              {resumen.por_sensor.map((b) => (
                <option key={b.key} value={b.key}>
                  {b.key} ({n(b.count)})
                </option>
              ))}
            </select>
            {(filtros.severidad || filtros.tactica || filtros.sensor) && (
              <button
                onClick={() =>
                  filtrar({ severidad: undefined, tactica: undefined, sensor: undefined })
                }
                className="text-[11px] text-white/45 hover:text-white/80 underline underline-offset-2 ml-1"
              >
                {t.triage.clear}
              </button>
            )}
          </div>
        </div>

        <Listado
          listado={listado}
          filtros={filtros}
          elegida={elegida}
          nuevas={nuevas}
          onElegir={setElegida}
          onPagina={(desde) => setFiltros((f) => ({ ...f, desde }))}
          tacticName={tacticName}
        />
      </div>

      <Cajon
        abierto={elegida !== null}
        onCerrar={() => setElegida(null)}
        titulo={t.triage.detail.title}
        pie={
          detalle &&
          escribe &&
          (detalle.revision?.a_ciegas ? (
            <p className="text-[11px] text-white/50 text-center leading-relaxed">
              {t.triage.verdict.blindLocked}
            </p>
          ) : (
            <button
              onClick={() => setRevisando(true)}
              className="w-full flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[12.5px] font-medium bg-[var(--honey-amber)] text-[var(--sobre-ambar)] hover:brightness-110 transition"
            >
              <PencilLine className="w-4 h-4" />
              {detalle.revision ? t.triage.verdict.change : t.triage.detail.review}
            </button>
          ))
        }
      >
        {errorDetalle && (
          <div className="text-[12px] text-[var(--agent-coral)]">{errorDetalle}</div>
        )}
        {!detalle && !errorDetalle && (
          <div className="flex flex-col gap-3 animate-pulse">
            <div className="h-36 rounded-xl bg-white/[0.04]" />
            <div className="h-24 rounded-xl bg-white/[0.03]" />
          </div>
        )}
        {detalle && <Detalle detalle={detalle} tacticName={tacticName} onAbrir={setElegida} />}
      </Cajon>

      {detalle && (
        <ModalVeredicto
          key={`${detalle.doc_id}-${revisando}`}
          detalle={detalle}
          abierto={revisando}
          onCerrar={() => setRevisando(false)}
          onGuardado={() => {
            cargarDetalle(detalle.doc_id);
            cargarListado();
            recargarResumen();
          }}
          tacticName={tacticName}
        />
      )}

      <RevisionACiegas
        abierto={aCiegas}
        onCerrar={() => setACiegas(false)}
        onGuardado={() => {
          cargarListado();
          recargarResumen();
        }}
        tacticName={tacticName}
      />
    </section>
  );
}

function Listado({
  listado,
  filtros,
  elegida,
  nuevas,
  onElegir,
  onPagina,
  tacticName,
}: {
  listado: ListadoDecisiones | null;
  filtros: FiltrosDecisiones;
  elegida: string | null;
  nuevas: Set<string>;
  onElegir: (docId: string) => void;
  onPagina: (desde: number) => void;
  tacticName: (key: string) => string;
}) {
  const { t } = useI18n();
  if (!listado) return <div className="h-[320px] animate-pulse bg-white/[0.02]" />;

  const desde = filtros.desde;
  const hasta = Math.min(desde + filtros.tamano, listado.total);

  if (listado.items.length === 0) {
    const vacioDePendientes = filtros.estado === 'pendientes';
    return (
      <div className="px-6 py-10 flex flex-col items-center text-center gap-2">
        {vacioDePendientes ? (
          <CheckCircle2 className="w-7 h-7 text-[var(--neural-teal)]" />
        ) : (
          <Inbox className="w-7 h-7 text-white/30" />
        )}
        <div className="text-[13px] text-white/80">
          {vacioDePendientes ? t.triage.emptyPendingTitle : t.triage.empty}
        </div>
        {vacioDePendientes && (
          <p className="text-[11.5px] text-white/50 max-w-md leading-relaxed">
            {t.triage.emptyPendingText}
          </p>
        )}
      </div>
    );
  }

  return (
    <>
      <div className="hidden sm:grid grid-cols-[96px_minmax(0,1fr)_auto] gap-3 px-4 py-2 border-b border-white/5 rotulo">
        <span>{t.triage.when}</span>
        <span>{t.triage.event}</span>
        <span>
          {t.triage.severity} / {t.triage.tactic}
        </span>
      </div>
      <ul>
        {listado.items.map((d) => (
          <Fila
            key={d.doc_id}
            d={d}
            activa={elegida === d.doc_id}
            nueva={nuevas.has(d.doc_id)}
            onClick={() => onElegir(d.doc_id)}
            tacticName={tacticName}
          />
        ))}
      </ul>
      {listado.total > 0 && (
        <div className="flex items-center justify-between gap-2 flex-wrap px-4 py-2.5 border-t border-white/5 text-[10.5px] text-white/45">
          <span className="font-data">
            {t.triage.page(n(desde + 1), n(hasta), n(listado.total))}
          </span>
          <span className="flex gap-2">
            <button
              disabled={desde === 0}
              onClick={() => onPagina(Math.max(desde - filtros.tamano, 0))}
              className="px-2.5 py-1 rounded-md ring-1 ring-white/10 disabled:opacity-30 hover:text-white/85"
            >
              {t.triage.prev}
            </button>
            <button
              disabled={hasta >= listado.total}
              onClick={() => onPagina(desde + filtros.tamano)}
              className="px-2.5 py-1 rounded-md ring-1 ring-white/10 disabled:opacity-30 hover:text-white/85"
            >
              {t.triage.next}
            </button>
          </span>
        </div>
      )}
    </>
  );
}

function Fila({
  d,
  activa,
  nueva,
  onClick,
  tacticName,
}: {
  d: FilaDecision;
  activa: boolean;
  nueva: boolean;
  onClick: () => void;
  tacticName: (key: string) => string;
}) {
  const { t } = useI18n();
  const pendiente = d.requiere_revision && !d.revision;
  const camino = caminoDe(d);
  return (
    <li className={nueva ? 'fila-nueva' : undefined}>
      <button
        onClick={onClick}
        className={`w-full grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[96px_minmax(0,1fr)_auto] gap-3 items-center px-4 py-2.5 text-left border-b border-white/[0.04] transition ${
          activa ? 'bg-white/[0.06]' : 'hover:bg-white/[0.03]'
        }`}
      >
        <span className="hidden sm:block font-data text-[10px] text-white/45">
          {fechaHora(d.momento)}
        </span>
        <span className="min-w-0 flex items-start gap-2.5">
          <camino.icono
            className="w-3.5 h-3.5 shrink-0 mt-0.5"
            style={{ color: camino.color }}
            aria-label={t.triage.engine.paths[camino.clave]}
          />
          <span className="min-w-0">
            <span className="block truncate text-[11.5px] text-white/80 font-data">
              {d.resumen}
            </span>
            <span className="flex items-center gap-2 flex-wrap text-[10px] text-white/40 mt-0.5">
              <span className="sm:hidden font-data">{fechaHora(d.momento)}</span>
              <span>{t.triage.engine.paths[camino.clave]}</span>
              {pendiente && (
                <span className="flex items-center gap-1 text-[var(--agent-coral)]">
                  <AlertCircle className="w-3 h-3" />
                  {t.triage.needsReview}
                </span>
              )}
              {d.revision && (
                <span className="flex items-center gap-1 text-[var(--neural-teal)]">
                  <CheckCircle2 className="w-3 h-3" />
                  {d.revision.veredicto === 'confirma'
                    ? t.triage.verdict.confirmed
                    : t.triage.verdict.corrected}
                </span>
              )}
            </span>
          </span>
        </span>
        <span className="flex flex-col sm:flex-row items-end sm:items-center gap-1 sm:gap-2.5 justify-end">
          <ChipSeveridad severidad={d.severidad} />
          <span
            className="text-[10.5px] sm:w-36 truncate text-right"
            style={{
              color: d.tactica_mitre ? tacticColor(d.tactica_mitre) : 'rgb(var(--tinta) / 0.35)',
            }}
          >
            {d.tactica_mitre ? tacticName(d.tactica_mitre) : t.triage.noTactic}
          </span>
        </span>
      </button>
    </li>
  );
}
