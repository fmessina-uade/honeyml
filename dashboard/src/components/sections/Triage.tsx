import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, ChevronRight, Copy, Sparkles, X } from 'lucide-react';
import {
  api,
  type DetalleDecision,
  type FilaDecision,
  type FiltrosDecisiones,
  type ListadoDecisiones,
  type ResumenTriaje,
  type Revision,
} from '../../lib/api';
import { dec, duracion, fechaHora, n } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import Reveal from '../Reveal';
import EngineLive from '../EngineLive';
import { tacticColor } from './SessionReplay';
import { OBSERVED } from './MitreMatrix';

// La escala del motor, de menor a mayor. Es la de `severidad.py`, y el panel la necesita para
// ordenar las barras y para que el analista corrija con los mismos niveles.
const SEVERIDADES = ['informativo', 'bajo', 'medio', 'alto', 'critico'] as const;

const SEVERITY_COLOR: Record<string, string> = {
  informativo: 'var(--ghost-slate)',
  bajo: 'var(--neural-teal)',
  medio: 'var(--honey-amber)',
  alto: 'var(--agent-coral)',
  critico: '#ef4444',
};

// Cómo pide la API las decisiones sin táctica, en los filtros.
const SIN_TACTICA = 'ninguna';

const TAMANO = 25;

const FILTROS_INICIALES: FiltrosDecisiones = { estado: 'todas', desde: 0, tamano: TAMANO };

const tarjeta = 'rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4';
const rotulo = 'text-[9px] uppercase tracking-wider text-white/35';

/**
 * Lo que decidió el motor de triaje, y el lugar donde el analista tiene la última palabra.
 *
 * Sigue el caso de uso de revisión: del listado se elige una decisión, se ven los atributos
 * normalizados del evento, la severidad y la táctica, la justificación con su evidencia, y cómo se
 * llegó a ella. Lo que el motor no pudo concluir, o concluyó con parte del contexto faltante, llega
 * marcado como pendiente, y el veredicto del analista queda guardado al lado de la decisión sin
 * modificarla.
 */
export default function Triage() {
  const { t } = useI18n();
  const [resumen, setResumen] = useState<ResumenTriaje | null>(null);
  const [filtros, setFiltros] = useState<FiltrosDecisiones>(FILTROS_INICIALES);
  const [listado, setListado] = useState<ListadoDecisiones | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elegida, setElegida] = useState<string | null>(null);
  const listadoRef = useRef<HTMLDivElement>(null);

  // Una decisión elegida desde el motor en vivo se abre donde está el detalle, más abajo, así que
  // hay que llevar la vista hasta ahí.
  const elegirDesdeElMotor = (docId: string) => {
    setElegida(docId);
    requestAnimationFrame(() =>
      listadoRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
    );
  };

  const cargarResumen = useCallback(() => {
    api
      .triaje()
      .then(setResumen)
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  const cargarListado = useCallback(() => {
    api
      .decisiones(filtros)
      .then(setListado)
      .catch((e) => setError(String(e.message ?? e)));
  }, [filtros]);

  useEffect(cargarResumen, [cargarResumen]);
  useEffect(cargarListado, [cargarListado]);

  // Los números y el listado se refrescan solos mientras la sección está abierta. El listado solo
  // en la primera página: refrescar la cuarta mientras alguien la lee le movería las filas.
  useEffect(() => {
    const id = window.setInterval(() => {
      cargarResumen();
      if (filtros.desde === 0) cargarListado();
    }, 60_000);
    return () => window.clearInterval(id);
  }, [cargarResumen, cargarListado, filtros.desde]);

  // Cambiar un filtro vuelve a la primera página: quedarse en la cuarta de un listado que ahora
  // tiene dos muestra una lista vacía que parece un error.
  const filtrar = (cambio: Partial<FiltrosDecisiones>) =>
    setFiltros((f) => ({ ...f, ...cambio, desde: 0 }));

  const tacticName = (key: string) =>
    key === SIN_TACTICA
      ? t.triage.noTactic
      : (t.tactics[key as keyof typeof t.tactics]?.name ?? key);

  if (error && !resumen) {
    return (
      <div className={`${tarjeta} flex gap-3`}>
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
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 animate-pulse">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-[104px] rounded-xl bg-white/[0.03] ring-1 ring-white/5" />
        ))}
      </div>
    );
  }

  const maxSev = Math.max(...resumen.por_severidad.map((b) => b.count), 1);
  const maxTac = Math.max(...resumen.por_tactica.map((b) => b.count), 1);
  const hayFiltros = Boolean(
    filtros.severidad || filtros.tactica || filtros.sensor || filtros.estado !== 'todas',
  );

  return (
    <section className="flex flex-col gap-4">
      {/* El motor trabajando, que es lo primero que hay que ver */}
      <EngineLive resumen={resumen} tacticName={tacticName} onElegir={elegirDesdeElMotor} />

      {/* Los cuatro números del motor */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Reveal>
          <div className={`${tarjeta} h-full`}>
            <div className={rotulo}>{t.triage.decisions}</div>
            <div className="font-data text-2xl text-white mt-2">{n(resumen.total)}</div>
            <div className="text-[10px] text-white/45 mt-1.5 leading-relaxed">
              {n(resumen.razonadas)} {t.triage.reasoned}, {n(resumen.copiadas)} {t.triage.copied}
            </div>
          </div>
        </Reveal>
        <Reveal delay={60}>
          <div className={`${tarjeta} h-full`}>
            <div className={rotulo}>{t.triage.cost}</div>
            <div className="font-data text-2xl text-white mt-2">
              USD {dec(resumen.costo_usd, 2)}
            </div>
            <div className="text-[10px] text-white/45 mt-1.5 leading-relaxed">
              {n(resumen.corregidas_por_el_motor)} {t.triage.correctedByEngine}
            </div>
          </div>
        </Reveal>
        <Reveal delay={120}>
          <div className={`${tarjeta} h-full`}>
            <div className={rotulo}>{t.triage.conclusion}</div>
            {resumen.conclusion.mediana_s !== null ? (
              <div className="flex items-baseline gap-3 mt-2">
                <span className="font-data text-2xl text-white">
                  {duracion(resumen.conclusion.mediana_s)}
                </span>
                <span className="text-[10px] text-white/40">{t.triage.median}</span>
                {resumen.conclusion.p90_s !== null && (
                  <span className="font-data text-[11px] text-white/55">
                    {duracion(resumen.conclusion.p90_s)}{' '}
                    <span className="text-white/35">{t.triage.p90}</span>
                  </span>
                )}
              </div>
            ) : (
              <div className="text-[13px] text-white/40 mt-2">{t.triage.noData}</div>
            )}
            <div className="text-[10px] text-white/45 mt-1.5 leading-relaxed">
              {t.triage.conclusionNote(resumen.conclusion.ventana_dias)}
            </div>
          </div>
        </Reveal>
        <Reveal delay={180}>
          <button
            onClick={() => filtrar({ estado: 'pendientes' })}
            className={`${tarjeta} h-full w-full text-left transition hover:bg-white/[0.05]`}
            style={
              resumen.revision.pendientes
                ? { boxShadow: 'inset 0 0 0 1px rgba(255,107,53,0.35)' }
                : undefined
            }
          >
            <div className={rotulo}>{t.triage.pending}</div>
            <div
              className="font-data text-2xl mt-2"
              style={{
                color: resumen.revision.pendientes ? 'var(--agent-coral)' : 'white',
              }}
            >
              {n(resumen.revision.pendientes)}
            </div>
            <div className="text-[10px] text-white/45 mt-1.5 leading-relaxed">
              {t.triage.pendingNote(n(resumen.revision.requieren))}, {n(resumen.revision.revisadas)}{' '}
              {t.triage.reviewed.toLowerCase()}
            </div>
          </button>
        </Reveal>
      </div>

      {/* Distribución: severidad y táctica, que además filtran el listado */}
      <div className="grid md:grid-cols-2 gap-3">
        <Reveal delay={80}>
          <div className={`${tarjeta} h-full`}>
            <div className="flex items-baseline justify-between">
              <span className={rotulo}>{t.triage.bySeverity}</span>
              <span className="text-[9px] text-white/25">{t.triage.filterHint}</span>
            </div>
            <div className="flex flex-col gap-1.5 mt-3">
              {resumen.por_severidad.map((b) => (
                <Barra
                  key={b.key}
                  etiqueta={t.severities[b.key as keyof typeof t.severities] ?? b.key}
                  valor={b.count}
                  maximo={maxSev}
                  color={SEVERITY_COLOR[b.key] ?? 'var(--ghost-slate)'}
                  activa={filtros.severidad === b.key}
                  onClick={() =>
                    filtrar({ severidad: filtros.severidad === b.key ? undefined : b.key })
                  }
                />
              ))}
            </div>
          </div>
        </Reveal>
        <Reveal delay={140}>
          <div className={`${tarjeta} h-full`}>
            <span className={rotulo}>{t.triage.byTactic}</span>
            <div className="flex flex-col gap-1.5 mt-3">
              {resumen.por_tactica.map((b) => (
                <Barra
                  key={b.key}
                  etiqueta={tacticName(b.key)}
                  valor={b.count}
                  maximo={maxTac}
                  color={b.key === SIN_TACTICA ? 'rgba(255,255,255,0.18)' : tacticColor(b.key)}
                  activa={filtros.tactica === b.key}
                  onClick={() =>
                    filtrar({ tactica: filtros.tactica === b.key ? undefined : b.key })
                  }
                />
              ))}
            </div>
          </div>
        </Reveal>
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap items-center gap-2">
        {(['todas', 'pendientes', 'revisadas'] as const).map((e) => (
          <button
            key={e}
            onClick={() => filtrar({ estado: e })}
            className={`rounded-full px-3 py-1 text-[11px] ring-1 transition ${
              filtros.estado === e
                ? 'bg-[var(--honey-amber)]/15 text-[var(--honey-amber)] ring-[var(--honey-amber)]/40'
                : 'text-white/50 ring-white/10 hover:text-white/80'
            }`}
          >
            {t.triage.state[e]}
          </button>
        ))}
        <Selector
          etiqueta={t.triage.sensor}
          valor={filtros.sensor}
          opciones={resumen.por_sensor.map((b) => ({ valor: b.key, texto: b.key }))}
          cualquiera={t.triage.any}
          onChange={(v) => filtrar({ sensor: v })}
        />
        {hayFiltros && (
          <button
            onClick={() => setFiltros(FILTROS_INICIALES)}
            className="text-[11px] text-white/40 hover:text-white/75 underline underline-offset-2"
          >
            {t.triage.clear}
          </button>
        )}
      </div>

      {/* Listado y, al lado, la decisión elegida */}
      <div
        ref={listadoRef}
        className={`grid gap-3 items-start scroll-mt-4 ${elegida ? 'xl:grid-cols-[minmax(0,1fr)_460px]' : ''}`}
      >
        <Listado
          listado={listado}
          filtros={filtros}
          elegida={elegida}
          onElegir={setElegida}
          onPagina={(desde) => setFiltros((f) => ({ ...f, desde }))}
          tacticName={tacticName}
        />
        {elegida && (
          <Detalle
            key={elegida}
            docId={elegida}
            onCerrar={() => setElegida(null)}
            onAbrir={setElegida}
            onRevisada={() => {
              cargarResumen();
              cargarListado();
            }}
            tacticName={tacticName}
          />
        )}
      </div>
    </section>
  );
}

function Barra({
  etiqueta,
  valor,
  maximo,
  color,
  activa,
  onClick,
}: {
  etiqueta: string;
  valor: number;
  maximo: number;
  color: string;
  activa: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-3 rounded-md px-1.5 py-0.5 text-left transition ${
        activa ? 'bg-white/[0.06]' : 'hover:bg-white/[0.03]'
      }`}
    >
      <span className="w-40 shrink-0 truncate text-[11px] text-white/65 first-letter:uppercase">
        {etiqueta}
      </span>
      <span className="flex-1 h-1.5 rounded bg-white/5 overflow-hidden">
        <span
          className="block h-1.5 rounded transition-all duration-700"
          style={{ width: `${(valor / maximo) * 100}%`, background: color }}
        />
      </span>
      <span className="font-data text-[10px] text-white/45 w-16 text-right">{n(valor)}</span>
    </button>
  );
}

function Selector({
  etiqueta,
  valor,
  opciones,
  cualquiera,
  onChange,
}: {
  etiqueta: string;
  valor: string | undefined;
  opciones: { valor: string; texto: string }[];
  cualquiera: string;
  onChange: (v: string | undefined) => void;
}) {
  return (
    <label className="flex items-center gap-1.5 text-[11px] text-white/40">
      {etiqueta}
      <select
        value={valor ?? ''}
        onChange={(e) => onChange(e.target.value || undefined)}
        className="rounded-md bg-white/[0.04] ring-1 ring-white/10 px-2 py-1 text-[11px] text-white/75 outline-none"
      >
        <option value="">{cualquiera}</option>
        {opciones.map((o) => (
          <option key={o.valor} value={o.valor}>
            {o.texto}
          </option>
        ))}
      </select>
    </label>
  );
}

function ChipSeveridad({ severidad }: { severidad: string | null | undefined }) {
  const { t } = useI18n();
  if (!severidad) {
    return (
      <span className="rounded px-1.5 py-0.5 text-[10px] text-white/40 ring-1 ring-white/10">
        {t.triage.notConcluded}
      </span>
    );
  }
  const color = SEVERITY_COLOR[severidad] ?? 'var(--ghost-slate)';
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[10px] font-medium first-letter:uppercase"
      style={{ color, boxShadow: `inset 0 0 0 1px ${color}`, background: 'rgba(0,0,0,0.15)' }}
    >
      {t.severities[severidad as keyof typeof t.severities] ?? severidad}
    </span>
  );
}

function Listado({
  listado,
  filtros,
  elegida,
  onElegir,
  onPagina,
  tacticName,
}: {
  listado: ListadoDecisiones | null;
  filtros: FiltrosDecisiones;
  elegida: string | null;
  onElegir: (docId: string) => void;
  onPagina: (desde: number) => void;
  tacticName: (key: string) => string;
}) {
  const { t } = useI18n();
  if (!listado) {
    return (
      <div className="h-[320px] rounded-xl bg-white/[0.03] ring-1 ring-white/5 animate-pulse" />
    );
  }
  const desde = filtros.desde;
  const hasta = Math.min(desde + filtros.tamano, listado.total);

  return (
    <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] overflow-hidden">
      <div className="grid grid-cols-[88px_minmax(0,1fr)_auto] gap-3 px-3 py-2 border-b border-white/5 text-[9px] uppercase tracking-wider text-white/30">
        <span>{t.triage.when}</span>
        <span>{t.triage.event}</span>
        <span>
          {t.triage.severity} / {t.triage.tactic}
        </span>
      </div>
      {listado.items.length === 0 && (
        <div className="p-8 text-center text-[12px] text-white/40">{t.triage.empty}</div>
      )}
      {listado.items.map((d) => (
        <Fila
          key={d.doc_id}
          d={d}
          activa={elegida === d.doc_id}
          onClick={() => onElegir(d.doc_id)}
          tacticName={tacticName}
        />
      ))}
      {listado.total > 0 && (
        <div className="flex items-center justify-between px-3 py-2 border-t border-white/5 text-[10px] text-white/40">
          <span className="font-data">
            {t.triage.page(n(desde + 1), n(hasta), n(listado.total))}
          </span>
          <span className="flex gap-2">
            <button
              disabled={desde === 0}
              onClick={() => onPagina(Math.max(desde - filtros.tamano, 0))}
              className="px-2 py-0.5 rounded ring-1 ring-white/10 disabled:opacity-30 hover:text-white/80"
            >
              {t.triage.prev}
            </button>
            <button
              disabled={hasta >= listado.total}
              onClick={() => onPagina(desde + filtros.tamano)}
              className="px-2 py-0.5 rounded ring-1 ring-white/10 disabled:opacity-30 hover:text-white/80"
            >
              {t.triage.next}
            </button>
          </span>
        </div>
      )}
    </div>
  );
}

function Fila({
  d,
  activa,
  onClick,
  tacticName,
}: {
  d: FilaDecision;
  activa: boolean;
  onClick: () => void;
  tacticName: (key: string) => string;
}) {
  const { t } = useI18n();
  const pendiente = d.requiere_revision && !d.revision;
  return (
    <button
      onClick={onClick}
      className={`w-full grid grid-cols-[88px_minmax(0,1fr)_auto] gap-3 items-center px-3 py-2 text-left border-b border-white/[0.03] transition ${
        activa ? 'bg-white/[0.06]' : 'hover:bg-white/[0.03]'
      }`}
    >
      <span className="font-data text-[10px] text-white/40">{fechaHora(d.momento)}</span>
      <span className="min-w-0">
        <span className="block truncate text-[11px] text-white/75 font-data">{d.resumen}</span>
        <span className="flex items-center gap-1.5 text-[9px] text-white/30 mt-0.5">
          {d.copiada ? (
            <Copy className="w-2.5 h-2.5" aria-label={t.triage.copiedMark} />
          ) : (
            <Sparkles
              className="w-2.5 h-2.5 text-[var(--honey-amber)]"
              aria-label={t.triage.reasonedMark}
            />
          )}
          {d.copiada ? t.triage.copiedMark : t.triage.reasonedMark}
          {pendiente && (
            <span className="flex items-center gap-1 text-[var(--agent-coral)]">
              <AlertCircle className="w-2.5 h-2.5" />
              {t.triage.needsReview}
            </span>
          )}
          {d.revision && (
            <span className="flex items-center gap-1 text-[var(--neural-teal)]">
              <CheckCircle2 className="w-2.5 h-2.5" />
              {t.triage.reviewed}
            </span>
          )}
        </span>
      </span>
      <span className="flex items-center gap-2 justify-end">
        <ChipSeveridad severidad={d.severidad} />
        <span
          className="text-[10px] w-32 truncate text-right"
          style={{
            color: d.tactica_mitre ? tacticColor(d.tactica_mitre) : 'rgba(255,255,255,0.3)',
          }}
        >
          {d.tactica_mitre ? tacticName(d.tactica_mitre) : t.triage.noTactic}
        </span>
      </span>
    </button>
  );
}

function Detalle({
  docId,
  onCerrar,
  onAbrir,
  onRevisada,
  tacticName,
}: {
  docId: string;
  onCerrar: () => void;
  onAbrir: (docId: string) => void;
  onRevisada: () => void;
  tacticName: (key: string) => string;
}) {
  const { t } = useI18n();
  const [detalle, setDetalle] = useState<DetalleDecision | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(() => {
    api
      .decision(docId)
      .then(setDetalle)
      .catch((e) => setError(String(e.message ?? e)));
  }, [docId]);
  useEffect(cargar, [cargar]);

  return (
    <aside className="rounded-xl ring-1 ring-white/10 bg-[#0f141b] p-4 xl:sticky xl:top-0 xl:max-h-[calc(100vh-3rem)] overflow-y-auto thin-scroll flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <span className="font-data text-[10px] text-white/35 break-all">{docId}</span>
        <button
          onClick={onCerrar}
          aria-label={t.triage.detail.close}
          className="text-white/40 hover:text-white/80"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {error && <div className="text-[11px] text-[var(--agent-coral)]">{error}</div>}
      {!detalle && !error && <div className="h-40 rounded-lg bg-white/[0.03] animate-pulse" />}

      {detalle && (
        <>
          <Recorrido detalle={detalle} />
          <Clasificacion detalle={detalle} tacticName={tacticName} />
          <Veredicto
            detalle={detalle}
            tacticName={tacticName}
            onGuardado={() => {
              cargar();
              onRevisada();
            }}
          />
          <Ciclo detalle={detalle} onAbrir={onAbrir} />
          <Atributos evento={detalle.evento} />
        </>
      )}
    </aside>
  );
}

function Clasificacion({
  detalle,
  tacticName,
}: {
  detalle: DetalleDecision;
  tacticName: (key: string) => string;
}) {
  const { t } = useI18n();
  const d = detalle.decision.decision;
  const nivel = (k: string) => t.severities[k as keyof typeof t.severities] ?? k;
  return (
    <div className="flex flex-col gap-3">
      <div>
        <div className={rotulo}>{t.triage.detail.classification}</div>
        <div className="text-[12px] text-white/80 mt-1.5 font-data">
          {detalle.decision.evento.resumen}
        </div>
      </div>
      {d.severidad ? (
        <div className="flex flex-wrap items-center gap-2">
          <ChipSeveridad severidad={d.severidad} />
          <span
            className="text-[11px]"
            style={{
              color: d.tactica_mitre ? tacticColor(d.tactica_mitre) : 'rgba(255,255,255,0.4)',
            }}
          >
            {d.tactica_mitre ? tacticName(d.tactica_mitre) : t.triage.noTactic}
          </span>
          {d.confianza !== undefined && (
            <span className="font-data text-[10px] text-white/40">
              {t.triage.detail.confidence} {dec(d.confianza, 2)}
            </span>
          )}
        </div>
      ) : (
        <div className="text-[11px] text-white/50">{t.triage.detail.notConcluded}</div>
      )}
      <div className="text-[10px] text-white/35">
        {t.triage.detail.bounds(nivel(d.piso), nivel(d.techo))}
      </div>
      {d.justificacion && (
        <div>
          <div className={rotulo}>{t.triage.detail.justification}</div>
          <p className="text-[12px] text-white/70 mt-1.5 leading-relaxed">{d.justificacion}</p>
        </div>
      )}
      {d.evidencia && d.evidencia.length > 0 && (
        <div>
          <div className={rotulo}>{t.triage.detail.evidence}</div>
          <ul className="mt-1.5 flex flex-col gap-1">
            {d.evidencia.map((e, i) => (
              <li key={i} className="text-[11px] text-white/60 leading-relaxed pl-3 relative">
                <span className="absolute left-0 top-[7px] w-1 h-1 rounded-full bg-white/30" />
                {e}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Veredicto({
  detalle,
  tacticName,
  onGuardado,
}: {
  detalle: DetalleDecision;
  tacticName: (key: string) => string;
  onGuardado: () => void;
}) {
  const { t } = useI18n();
  const v = t.triage.verdict;
  const delMotor = detalle.decision.decision;
  const revision = detalle.revision;
  const [abierto, setAbierto] = useState(!revision);
  const [corrigiendo, setCorrigiendo] = useState(false);
  const [severidad, setSeveridad] = useState(delMotor.severidad ?? 'medio');
  const [tactica, setTactica] = useState(delMotor.tactica_mitre ?? '');
  const [nota, setNota] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enviar = (cuerpo: Parameters<typeof api.revisar>[1]) => {
    setGuardando(true);
    setError(null);
    api
      .revisar(detalle.doc_id, cuerpo)
      .then(() => {
        setAbierto(false);
        setCorrigiendo(false);
        onGuardado();
      })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setGuardando(false));
  };

  const pendiente = detalle.decision.ciclo.requiere_revision && !revision;

  return (
    <div
      className="rounded-lg p-3 ring-1"
      style={{
        background: pendiente ? 'rgba(255,107,53,0.06)' : 'rgba(255,255,255,0.02)',
        borderColor: 'transparent',
        boxShadow: `inset 0 0 0 1px ${pendiente ? 'rgba(255,107,53,0.35)' : 'rgba(255,255,255,0.08)'}`,
      }}
    >
      <div className={rotulo}>{v.title}</div>
      <p className="text-[10px] text-white/40 mt-1 leading-relaxed">{v.explain}</p>

      {revision && !abierto && <RevisionGuardada r={revision} tacticName={tacticName} />}
      {revision && !abierto && (
        <button
          onClick={() => setAbierto(true)}
          className="mt-2 text-[11px] text-white/45 hover:text-white/80 underline underline-offset-2"
        >
          {v.change}
        </button>
      )}
      {!revision && !abierto && <div className="text-[11px] text-white/45 mt-2">{v.none}</div>}

      {abierto && (
        <div className="flex flex-col gap-2 mt-3">
          <textarea
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            placeholder={v.note}
            maxLength={2000}
            rows={2}
            className="rounded-md bg-white/[0.04] ring-1 ring-white/10 px-2 py-1.5 text-[11px] text-white/80 outline-none resize-y"
          />
          {corrigiendo && (
            <div className="flex flex-wrap gap-2">
              <select
                value={severidad}
                onChange={(e) => setSeveridad(e.target.value)}
                className="rounded-md bg-white/[0.04] ring-1 ring-white/10 px-2 py-1 text-[11px] text-white/80 outline-none"
              >
                {SEVERIDADES.map((s) => (
                  <option key={s} value={s}>
                    {t.severities[s]}
                  </option>
                ))}
              </select>
              <select
                value={tactica}
                onChange={(e) => setTactica(e.target.value)}
                className="rounded-md bg-white/[0.04] ring-1 ring-white/10 px-2 py-1 text-[11px] text-white/80 outline-none"
              >
                <option value="">{t.triage.noTactic}</option>
                {OBSERVED.map((tac) => (
                  <option key={tac} value={tac}>
                    {tacticName(tac)}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {!corrigiendo && (
              <button
                disabled={guardando || !delMotor.severidad}
                title={!delMotor.severidad ? v.cannotConfirm : undefined}
                onClick={() => enviar({ veredicto: 'confirma', nota })}
                className="rounded-md px-3 py-1 text-[11px] bg-[var(--neural-teal)]/15 text-[var(--neural-teal)] ring-1 ring-[var(--neural-teal)]/40 disabled:opacity-35"
              >
                {v.confirm}
              </button>
            )}
            {!corrigiendo ? (
              <button
                disabled={guardando}
                onClick={() => setCorrigiendo(true)}
                className="rounded-md px-3 py-1 text-[11px] bg-[var(--honey-amber)]/15 text-[var(--honey-amber)] ring-1 ring-[var(--honey-amber)]/40"
              >
                {v.correct}
              </button>
            ) : (
              <button
                disabled={guardando}
                onClick={() =>
                  enviar({
                    veredicto: 'corrige',
                    severidad,
                    tactica_mitre: tactica || null,
                    nota,
                  })
                }
                className="rounded-md px-3 py-1 text-[11px] bg-[var(--honey-amber)]/15 text-[var(--honey-amber)] ring-1 ring-[var(--honey-amber)]/40"
              >
                {guardando ? v.saving : v.save}
              </button>
            )}
            {(corrigiendo || revision) && (
              <button
                disabled={guardando}
                onClick={() => {
                  setCorrigiendo(false);
                  setAbierto(!revision);
                }}
                className="rounded-md px-3 py-1 text-[11px] text-white/45 ring-1 ring-white/10 hover:text-white/75"
              >
                {v.cancel}
              </button>
            )}
          </div>
          {!delMotor.severidad && (
            <div className="text-[10px] text-white/40">{v.cannotConfirm}</div>
          )}
          {error && <div className="text-[11px] text-[var(--agent-coral)]">{error}</div>}
        </div>
      )}
    </div>
  );
}

function RevisionGuardada({ r, tacticName }: { r: Revision; tacticName: (key: string) => string }) {
  const { t } = useI18n();
  const v = t.triage.verdict;
  return (
    <div className="mt-2 flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5 text-[11px] text-[var(--neural-teal)]">
        <CheckCircle2 className="w-3 h-3" />
        {r.veredicto === 'confirma' ? v.confirmed : v.corrected}
        <span className="font-data text-[9px] text-white/30">{fechaHora(r['@timestamp'])}</span>
      </div>
      {r.veredicto === 'corrige' && (
        <div className="flex items-center gap-2">
          <ChipSeveridad severidad={r.severidad} />
          <span className="text-[11px] text-white/60">
            {r.tactica_mitre ? tacticName(r.tactica_mitre) : t.triage.noTactic}
          </span>
        </div>
      )}
      {r.nota && <p className="text-[11px] text-white/55 leading-relaxed">{r.nota}</p>}
    </div>
  );
}

function Ciclo({
  detalle,
  onAbrir,
}: {
  detalle: DetalleDecision;
  onAbrir: (docId: string) => void;
}) {
  const { t } = useI18n();
  const c = detalle.decision.ciclo;
  const m = detalle.decision.modelo;
  const d = t.triage.detail;
  const fallidas = c.consultas_fallidas ?? [];
  return (
    <div className="flex flex-col gap-2">
      <div className={rotulo}>{d.cycle}</div>
      {c.reutilizada_de ? (
        <div className="text-[11px] text-white/55 leading-relaxed">
          {d.copiedFrom}{' '}
          <button
            onClick={() => onAbrir(c.reutilizada_de as string)}
            className="font-data text-[10px] text-[var(--honey-amber)] hover:underline"
          >
            {c.reutilizada_de.slice(0, 12)} ({d.open})
          </button>
        </div>
      ) : (
        m.nombre && (
          <div className="font-data text-[10px] text-white/50">
            {d.model}: {m.nombre}
            {m.proveedor ? `, ${m.proveedor}` : ''}, {n(c.intentos)} {d.attempts}, {n(c.rechazos)}{' '}
            {d.rejections}
            {m.costo_usd !== undefined ? `, USD ${dec(m.costo_usd, 5)}` : ''}
          </div>
        )
      )}
      {c.motivo_de_corte && (
        <div className="text-[11px] text-white/55">
          {d.cutReason}: <span className="font-data">{c.motivo_de_corte}</span>
        </div>
      )}
      {fallidas.length > 0 && (
        <div className="rounded-md p-2 bg-[var(--agent-coral)]/5 ring-1 ring-[var(--agent-coral)]/25">
          <div className="text-[10px] text-[var(--agent-coral)]">
            {d.failed}: <span className="font-data">{fallidas.join(', ')}</span>
          </div>
          <div className="text-[10px] text-white/45 mt-0.5">{d.failedNote}</div>
        </div>
      )}
      {c.reproches.length > 0 && (
        <details className="text-[10px] text-white/45">
          <summary className="cursor-pointer">
            {d.reproaches} ({c.reproches.length})
          </summary>
          <ul className="mt-1 flex flex-col gap-1">
            {c.reproches.map((r, i) => (
              <li key={i} className="leading-relaxed">
                {r}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function Atributos({ evento }: { evento: DetalleDecision['evento'] }) {
  const { t } = useI18n();
  return (
    <div>
      <div className={rotulo}>{t.triage.detail.attributes}</div>
      {evento ? (
        <dl className="mt-1.5 grid grid-cols-[minmax(0,40%)_minmax(0,1fr)] gap-x-3 gap-y-1">
          {Object.entries(evento).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="font-data text-[10px] text-white/35 truncate">{k}</dt>
              <dd className="font-data text-[10px] text-white/70 break-all">
                {Array.isArray(v) ? v.join(', ') : String(v)}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-[11px] text-white/45 mt-1.5">{t.triage.detail.noEvent}</p>
      )}
    </div>
  );
}

function Recorrido({ detalle }: { detalle: DetalleDecision }) {
  const { t } = useI18n();
  const e = t.triage.engine;
  return (
    <div>
      <div className={rotulo}>{t.triage.detail.path}</div>
      <div className="flex flex-wrap items-center gap-1 mt-1.5">
        {detalle.camino.map((nodo, i) => (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <ChevronRight className="w-3 h-3 text-white/25" />}
            <span
              className="rounded px-1.5 py-0.5 text-[10px] font-mono-display ring-1"
              style={{
                color: nodo === 'inferencia' ? 'var(--agent-coral)' : 'rgba(255,255,255,0.7)',
                borderColor: 'transparent',
                boxShadow: `inset 0 0 0 1px ${
                  nodo === 'inferencia' ? 'rgba(255,107,53,0.45)' : 'rgba(255,255,255,0.12)'
                }`,
              }}
            >
              {e.nodes[nodo].name}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
