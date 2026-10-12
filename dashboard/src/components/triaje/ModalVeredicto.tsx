import { useState } from 'react';
import { CheckCircle2, PencilLine } from 'lucide-react';
import { api, type DetalleDecision } from '../../lib/api';
import { dec, fechaHora } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { Modal } from '../Superpuesto';
import { tacticColor } from '../sections/SessionReplay';
import { ChipSeveridad, sinTacticaConMotivo } from './comunes';
import { SelectorSeveridad, SelectorTactica } from './Selectores';

type Eleccion = 'confirma' | 'corrige';

/**
 * El veredicto del analista, en dos pasos: primero si la clasificación del motor es correcta, y
 * solo si no lo es, cuál corresponde. Separarlo así evita la pregunta más frecuente frente a un
 * formulario con todo a la vista: si hay que completar severidad y táctica aun estando de acuerdo.
 *
 * El rango que admite la evidencia se muestra como guía y no como límite: el motor no puede salir
 * de él, pero la última palabra es del analista. Lo que decide queda al lado de la decisión, que no
 * se modifica.
 */
export default function ModalVeredicto({
  detalle,
  abierto,
  onCerrar,
  onGuardado,
  tacticName,
}: {
  detalle: DetalleDecision;
  abierto: boolean;
  onCerrar: () => void;
  onGuardado: () => void;
  tacticName: (key: string) => string;
}) {
  const { t } = useI18n();
  const m = t.triage.modal;
  const delMotor = detalle.decision.decision;
  const previo = detalle.revision;

  const [eleccion, setEleccion] = useState<Eleccion | null>(null);
  const [severidad, setSeveridad] = useState<string>(delMotor.severidad ?? '');
  const [tactica, setTactica] = useState<string>(delMotor.tactica_mitre ?? '');
  const [nota, setNota] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listo, setListo] = useState(false);

  const nivel = (k: string) => t.severities[k as keyof typeof t.severities] ?? k;

  // Una corrección igual a lo que dijo el motor es una confirmación con otro nombre.
  const igualAlMotor =
    severidad === (delMotor.severidad ?? '') && tactica === (delMotor.tactica_mitre ?? '');
  const puedeGuardar =
    !guardando &&
    (eleccion === 'confirma' || (eleccion === 'corrige' && !!severidad && !igualAlMotor));

  const guardar = () => {
    if (!eleccion) return;
    setGuardando(true);
    setError(null);
    const cuerpo =
      eleccion === 'confirma'
        ? { veredicto: 'confirma' as const, nota }
        : {
            veredicto: 'corrige' as const,
            severidad,
            tactica_mitre: tactica || null,
            nota,
          };
    api
      .revisar(detalle.doc_id, cuerpo)
      .then(() => {
        setListo(true);
        onGuardado();
      })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setGuardando(false));
  };

  const pie = listo ? (
    <div className="flex justify-end">
      <button
        onClick={onCerrar}
        className="rounded-lg px-4 py-2 text-[12px] bg-white/10 text-white/85 hover:bg-white/15 transition"
      >
        {m.close}
      </button>
    </div>
  ) : (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <span className="text-[10.5px] text-white/40">
        {eleccion === 'corrige' && igualAlMotor ? m.sameAsEngine : m.untouched}
      </span>
      <div className="flex gap-2 ml-auto">
        <button
          onClick={onCerrar}
          className="rounded-lg px-3.5 py-2 text-[12px] text-white/60 ring-1 ring-white/10 hover:text-white/85 transition"
        >
          {t.triage.verdict.cancel}
        </button>
        <button
          onClick={guardar}
          disabled={!puedeGuardar}
          className="rounded-lg px-4 py-2 text-[12px] font-medium transition disabled:opacity-35 disabled:cursor-not-allowed bg-[var(--honey-amber)] text-[var(--sobre-ambar)] hover:brightness-110"
        >
          {guardando ? t.triage.verdict.saving : m.save}
        </button>
      </div>
    </div>
  );

  return (
    <Modal abierto={abierto} onCerrar={onCerrar} titulo={m.title} pie={pie}>
      {listo ? (
        <div className="flex flex-col items-center text-center gap-3 py-8">
          <CheckCircle2 className="w-10 h-10 text-[var(--neural-teal)]" />
          <div className="titulo text-[15px]">{m.saved}</div>
          <p className="text-[12px] text-white/55 max-w-sm leading-relaxed">{m.savedHint}</p>
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          {/* Lo que dijo el motor, para tenerlo a la vista al decidir */}
          <div className="rounded-xl bg-white/[0.03] ring-1 ring-white/[0.07] p-3.5">
            <div className="rotulo mb-2">{m.engineSays}</div>
            <div className="flex flex-wrap items-center gap-2">
              <ChipSeveridad severidad={delMotor.severidad} grande />
              <span
                className="text-[12px]"
                style={{
                  color: delMotor.tactica_mitre
                    ? tacticColor(delMotor.tactica_mitre)
                    : 'rgb(var(--tinta) / 0.45)',
                }}
              >
                {delMotor.tactica_mitre
                  ? tacticName(delMotor.tactica_mitre)
                  : sinTacticaConMotivo(t, delMotor.motivo_sin_tactica)}
              </span>
              {delMotor.confianza !== undefined && (
                <span className="font-data text-[10px] text-white/40">
                  {t.triage.detail.confidence} {dec(delMotor.confianza, 2)}
                </span>
              )}
            </div>
            <div className="font-data text-[11px] text-white/55 mt-2 break-all">
              {detalle.decision.evento.resumen}
            </div>
            {delMotor.justificacion && (
              <p className="text-[12px] text-white/70 mt-2 leading-relaxed line-clamp-3">
                {delMotor.justificacion}
              </p>
            )}
          </div>

          {previo && (
            <div className="text-[11px] text-white/55 rounded-lg bg-[var(--neural-teal)]/[0.07] ring-1 ring-[var(--neural-teal)]/25 px-3 py-2">
              {m.alreadyReviewed(
                previo.veredicto === 'confirma' ? m.confirmedShort : m.correctedShort,
                fechaHora(previo['@timestamp']),
              )}
            </div>
          )}

          {/* Primer paso: ¿está bien? */}
          <div>
            <div className="text-[13px] text-white/85 mb-2.5">{m.question}</div>
            <div className="grid sm:grid-cols-2 gap-2.5" role="radiogroup" aria-label={m.question}>
              {(
                [
                  {
                    valor: 'confirma',
                    icono: CheckCircle2,
                    color: 'var(--neural-teal)',
                    titulo: m.yes,
                    ayuda: delMotor.severidad ? m.yesHint : t.triage.verdict.cannotConfirm,
                    deshabilitada: !delMotor.severidad,
                  },
                  {
                    valor: 'corrige',
                    icono: PencilLine,
                    color: 'var(--honey-amber)',
                    titulo: m.no,
                    ayuda: m.noHint,
                    deshabilitada: false,
                  },
                ] as const
              ).map((o, k) => {
                const elegida = eleccion === o.valor;
                return (
                  <button
                    key={o.valor}
                    role="radio"
                    aria-checked={elegida}
                    disabled={o.deshabilitada}
                    data-foco-inicial={k === 0 && !o.deshabilitada ? '' : undefined}
                    onClick={() => setEleccion(o.valor)}
                    className="flex items-start gap-3 rounded-xl p-3.5 text-left transition disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{
                      background: elegida
                        ? `color-mix(in srgb, ${o.color} 12%, transparent)`
                        : 'rgb(var(--tinta) / 0.03)',
                      boxShadow: `inset 0 0 0 ${elegida ? 1.5 : 1}px ${
                        elegida ? o.color : 'rgb(var(--tinta) / 0.1)'
                      }`,
                    }}
                  >
                    <o.icono className="w-5 h-5 shrink-0 mt-0.5" style={{ color: o.color }} />
                    <span>
                      <span className="block text-[13px] text-white/90">{o.titulo}</span>
                      <span className="block text-[11px] text-white/50 mt-0.5 leading-snug">
                        {o.ayuda}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Segundo paso, solo al corregir: qué corresponde */}
          {eleccion === 'corrige' && (
            <div className="section-in flex flex-col gap-5">
              <div>
                <div className="text-[13px] text-white/85">{m.severityQ}</div>
                <div className="text-[11px] text-white/45 mt-0.5 mb-2.5">
                  {m.rangeHint(nivel(delMotor.piso), nivel(delMotor.techo))}
                </div>
                <SelectorSeveridad
                  valor={severidad}
                  onElegir={setSeveridad}
                  piso={delMotor.piso}
                  techo={delMotor.techo}
                  rotulo={m.severityQ}
                  marcada={delMotor.severidad}
                  etiqueta={m.engineTag}
                />
              </div>

              <div>
                <div className="text-[13px] text-white/85 mb-2.5">{m.tacticQ}</div>
                <SelectorTactica
                  valor={tactica}
                  onElegir={setTactica}
                  rotulo={m.tacticQ}
                  tacticName={tacticName}
                  marcada={delMotor.tactica_mitre ?? null}
                  etiqueta={m.engineTag}
                />
              </div>
            </div>
          )}

          {eleccion && (
            <label className="section-in flex flex-col gap-1.5">
              <span className="text-[12px] text-white/70">{m.noteLabel}</span>
              <textarea
                value={nota}
                onChange={(e) => setNota(e.target.value)}
                placeholder={m.notePlaceholder}
                maxLength={2000}
                rows={2}
                className="rounded-lg bg-white/[0.04] ring-1 ring-white/10 focus:ring-white/25 px-3 py-2 text-[12px] text-white/85 placeholder:text-white/30 outline-none resize-y transition"
              />
            </label>
          )}

          {error && <div className="text-[11.5px] text-[var(--agent-coral)]">{error}</div>}
        </div>
      )}
    </Modal>
  );
}
