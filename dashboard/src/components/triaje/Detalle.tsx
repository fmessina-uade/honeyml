import { AlertCircle, CheckCircle2, ChevronDown, ChevronRight, CircleDashed } from 'lucide-react';
import type { ReactNode } from 'react';
import type { DetalleDecision, Revision } from '../../lib/api';
import { dec, duracion, fechaHora, n } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { tacticColor } from '../sections/SessionReplay';
import { ChipSeveridad, colorDeSeveridad } from './comunes';

function Seccion({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="rotulo">{titulo}</h3>
      {children}
    </section>
  );
}

/** Un bloque que arranca cerrado: el detalle técnico está, pero no compite con lo que se decide. */
function Desplegable({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <details className="group rounded-lg ring-1 ring-white/[0.07] bg-white/[0.02]">
      <summary className="flex items-center justify-between gap-2 cursor-pointer list-none px-3 py-2.5 text-[12px] text-white/70 hover:text-white/90">
        {titulo}
        <ChevronDown className="w-3.5 h-3.5 text-white/35 transition-transform group-open:rotate-180" />
      </summary>
      <div className="px-3 pb-3">{children}</div>
    </details>
  );
}

function VeredictoGuardado({ r, tacticName }: { r: Revision; tacticName: (k: string) => string }) {
  const { t } = useI18n();
  const v = t.triage.verdict;
  return (
    <div className="rounded-lg bg-[var(--neural-teal)]/[0.07] ring-1 ring-[var(--neural-teal)]/25 p-3 flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5 text-[12px] text-[var(--neural-teal)]">
        <CheckCircle2 className="w-3.5 h-3.5" />
        {r.veredicto === 'confirma' ? v.confirmed : v.corrected}
        {r.a_ciegas && (
          <span className="font-data text-[9.5px] px-1.5 py-0.5 rounded ring-1 ring-[var(--neural-teal)]/40">
            {v.blindTag}
          </span>
        )}
        <span className="font-data text-[10px] text-white/35 ml-auto">
          {fechaHora(r['@timestamp'])}
        </span>
      </div>
      {(r.veredicto === 'corrige' || r.a_ciegas) && (
        <div className="flex items-center gap-2 flex-wrap">
          <ChipSeveridad severidad={r.severidad} />
          <span className="text-[11px] text-white/65">
            {r.tactica_mitre ? tacticName(r.tactica_mitre) : t.triage.noTactic}
          </span>
        </div>
      )}
      {r.nota && <p className="text-[11.5px] text-white/60 leading-relaxed">{r.nota}</p>}
    </div>
  );
}

/**
 * El detalle de una decisión, ordenado por lo que el analista necesita para juzgarla: qué decidió,
 * por qué y cómo llegó. Los datos del ciclo y los atributos crudos del evento quedan plegados.
 */
export default function Detalle({
  detalle,
  tacticName,
  onAbrir,
}: {
  detalle: DetalleDecision;
  tacticName: (key: string) => string;
  onAbrir: (docId: string) => void;
}) {
  const { t } = useI18n();
  const d = t.triage.detail;
  const e = t.triage.engine;
  const doc = detalle.decision;
  const decision = doc.decision;
  const ciclo = doc.ciclo;
  const modelo = doc.modelo;
  const pendiente = !!ciclo.requiere_revision && !detalle.revision;
  const fallidas = ciclo.consultas_fallidas ?? [];
  const nivel = (k: string) => t.severities[k as keyof typeof t.severities] ?? k;

  const estado = detalle.revision
    ? { icono: CheckCircle2, color: 'var(--neural-teal)', texto: d.stateReviewed }
    : pendiente
      ? { icono: AlertCircle, color: 'var(--agent-coral)', texto: d.statePending }
      : { icono: CircleDashed, color: 'var(--ghost-slate)', texto: d.stateEngine };

  const momento = doc.evento.momento ? new Date(doc.evento.momento).getTime() : null;
  const decidida = new Date(doc['@timestamp']).getTime();
  const demora = momento && !ciclo.retriaje ? (decidida - momento) / 1000 : null;

  return (
    <div className="flex flex-col gap-5">
      {/* Lo que decidió */}
      <div
        className="rounded-xl p-4 ring-1 ring-white/[0.07]"
        style={{
          background: `linear-gradient(135deg, color-mix(in srgb, ${colorDeSeveridad(decision.severidad)} 9%, transparent), transparent 70%)`,
        }}
      >
        <div className="flex items-center gap-1.5 text-[11px] mb-3" style={{ color: estado.color }}>
          <estado.icono className="w-3.5 h-3.5" />
          {estado.texto}
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <ChipSeveridad severidad={decision.severidad} grande />
          <span
            className="text-[14px]"
            style={{
              color: decision.tactica_mitre
                ? tacticColor(decision.tactica_mitre)
                : 'rgb(var(--tinta) / 0.45)',
            }}
          >
            {decision.tactica_mitre ? tacticName(decision.tactica_mitre) : t.triage.noTactic}
          </span>
          {decision.confianza !== undefined && (
            <span className="font-data text-[10.5px] text-white/40">
              {d.confidence} {dec(decision.confianza, 2)}
            </span>
          )}
        </div>
        <div className="font-data text-[12px] text-white/75 mt-3 break-all leading-relaxed">
          {doc.evento.resumen}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 font-data text-[10px] text-white/40">
          <span>{d.eventAt(fechaHora(doc.evento.momento))}</span>
          <span>{d.decidedAt(fechaHora(doc['@timestamp']))}</span>
          {demora !== null && <span>{d.took(duracion(demora))}</span>}
        </div>
        <div className="text-[10.5px] text-white/40 mt-2">
          {d.bounds(nivel(decision.piso), nivel(decision.techo))}
        </div>
      </div>

      {detalle.revision && (
        <Seccion titulo={t.triage.verdict.title}>
          <VeredictoGuardado r={detalle.revision} tacticName={tacticName} />
        </Seccion>
      )}

      {fallidas.length > 0 && (
        <div className="rounded-lg p-3 bg-[var(--agent-coral)]/[0.06] ring-1 ring-[var(--agent-coral)]/25">
          <div className="text-[11.5px] text-[var(--agent-coral)]">
            {d.failed}: <span className="font-data">{fallidas.join(', ')}</span>
          </div>
          <div className="text-[11px] text-white/50 mt-1">{d.failedNote}</div>
        </div>
      )}

      <Seccion titulo={d.why}>
        {ciclo.reutilizada_de && (
          <div className="text-[11.5px] text-white/55 leading-relaxed">
            {d.copiedFrom}{' '}
            <button
              onClick={() => onAbrir(ciclo.reutilizada_de as string)}
              className="text-[var(--honey-amber)] hover:underline"
            >
              {d.seeOriginal}
            </button>
          </div>
        )}
        {decision.justificacion ? (
          <p className="text-[12.5px] text-white/80 leading-relaxed">{decision.justificacion}</p>
        ) : (
          <p className="text-[12px] text-white/50">{d.notConcluded}</p>
        )}
        {decision.evidencia && decision.evidencia.length > 0 && (
          <ul className="flex flex-col gap-1.5 mt-1">
            {decision.evidencia.map((ev, i) => (
              <li key={i} className="text-[11.5px] text-white/65 leading-relaxed pl-3.5 relative">
                <span className="absolute left-0 top-[7px] w-1.5 h-1.5 rounded-full bg-white/25" />
                {ev}
              </li>
            ))}
          </ul>
        )}
      </Seccion>

      <Seccion titulo={d.path}>
        <div className="flex flex-wrap items-center gap-1">
          {detalle.camino.map((nodo, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="w-3 h-3 text-white/25" />}
              <span
                className="rounded px-1.5 py-0.5 text-[10.5px] font-mono-display"
                style={{
                  color: nodo === 'inferencia' ? 'var(--agent-coral)' : 'rgb(var(--tinta) / 0.75)',
                  boxShadow: `inset 0 0 0 1px ${
                    nodo === 'inferencia'
                      ? 'color-mix(in srgb, var(--agent-coral) 50%, transparent)'
                      : 'rgb(var(--tinta) / 0.12)'
                  }`,
                }}
              >
                {e.nodes[nodo].name}
              </span>
            </span>
          ))}
        </div>
        <p className="text-[11px] text-white/45 leading-relaxed">
          {ciclo.reutilizada_de
            ? d.pathMemory
            : ciclo.motivo_de_corte === 'sin_contexto'
              ? d.pathNoContext
              : ciclo.rechazos
                ? d.pathRetry(ciclo.rechazos)
                : d.pathFull}
        </p>
      </Seccion>

      <div className="flex flex-col gap-2">
        <Desplegable titulo={d.cycle}>
          <dl className="grid grid-cols-[minmax(0,40%)_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[11px]">
            {(
              [
                [
                  d.model,
                  modelo.nombre
                    ? `${modelo.nombre}${modelo.proveedor ? `, ${modelo.proveedor}` : ''}`
                    : null,
                ],
                [d.attempts, n(ciclo.intentos)],
                [d.rejections, n(ciclo.rechazos)],
                [d.cost, modelo.costo_usd !== undefined ? `USD ${dec(modelo.costo_usd, 5)}` : null],
                [d.seconds, modelo.segundos !== undefined ? `${dec(modelo.segundos, 1)} s` : null],
                [d.cutReason, ciclo.motivo_de_corte],
                [d.signature, ciclo.firma],
              ] as [string, string | null][]
            )
              .filter(([, valor]) => valor !== null && valor !== '')
              .map(([clave, valor]) => (
                <div key={clave} className="contents">
                  <dt className="text-white/40">{clave}</dt>
                  <dd className="font-data text-white/75 break-all">{valor}</dd>
                </div>
              ))}
          </dl>
          {ciclo.reproches.length > 0 && (
            <div className="mt-3">
              <div className="rotulo mb-1">{d.reproaches}</div>
              <ul className="flex flex-col gap-1">
                {ciclo.reproches.map((r, i) => (
                  <li key={i} className="text-[11px] text-white/55 leading-relaxed">
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Desplegable>

        <Desplegable titulo={d.attributes}>
          {detalle.evento ? (
            <dl className="grid grid-cols-[minmax(0,40%)_minmax(0,1fr)] gap-x-3 gap-y-1">
              {Object.entries(detalle.evento).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="font-data text-[10px] text-white/40 truncate">{k}</dt>
                  <dd className="font-data text-[10px] text-white/75 break-all">
                    {Array.isArray(v) ? v.join(', ') : String(v)}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-[11px] text-white/50">{d.noEvent}</p>
          )}
        </Desplegable>

        <div className="font-data text-[9.5px] text-white/25 break-all px-1">{detalle.doc_id}</div>
      </div>
    </div>
  );
}
