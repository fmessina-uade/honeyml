import { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, ChevronDown, CircleSlash, EyeOff } from 'lucide-react';
import { api, type ItemACiegas, type Revision } from '../../lib/api';
import { fechaHora, n } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { Modal } from '../Superpuesto';
import { tacticColor } from '../sections/SessionReplay';
import { ChipSeveridad } from './comunes';
import { SelectorSeveridad, SelectorTactica } from './Selectores';

/**
 * La revisión a ciegas de la muestra con la que se mide al motor: una conducta por vez, con el
 * evento y sin lo que dijo el motor. Quien revisa elige severidad y táctica, guarda, y recién ahí
 * ve la clasificación del motor al lado de la suya.
 *
 * Es un recorrido aparte del veredicto común porque la bandeja y el detalle muestran la decisión
 * del motor antes de que se pueda opinar, y verla primero arrastra el juicio hacia ella. Por eso
 * tampoco se puede saltear una conducta: elegir cuáles revisar sesgaría la muestra.
 */
export default function RevisionACiegas({
  abierto,
  onCerrar,
  onGuardado,
  tacticName,
}: {
  abierto: boolean;
  onCerrar: () => void;
  onGuardado: () => void;
  tacticName: (key: string) => string;
}) {
  const { t } = useI18n();
  const b = t.triage.blind;
  const m = t.triage.modal;

  const [item, setItem] = useState<ItemACiegas | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [severidad, setSeveridad] = useState('');
  // null es que todavía no eligió; la cadena vacía, que eligió "ninguna"
  const [tactica, setTactica] = useState<string | null>(null);
  const [nota, setNota] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [resultado, setResultado] = useState<Revision | null>(null);

  const nivel = (k: string) => t.severities[k as keyof typeof t.severities] ?? k;

  const cargar = useCallback(() => {
    setItem(null);
    setError(null);
    setResultado(null);
    setSeveridad('');
    setTactica(null);
    setNota('');
    api
      .siguienteACiegas()
      .then(setItem)
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    if (abierto) cargar();
  }, [abierto, cargar]);

  const listo = !!severidad && tactica !== null;

  const guardar = () => {
    if (!item?.doc_id || !listo) return;
    setGuardando(true);
    setError(null);
    api
      .revisarACiegas(item.doc_id, { severidad, tactica_mitre: tactica || null, nota })
      .then((r) => {
        setResultado(r);
        onGuardado();
      })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setGuardando(false));
  };

  const progreso = item && (
    <span className="font-data text-[10.5px] text-white/45 ml-2 whitespace-nowrap">
      {b.progress(item.revisadas, item.total)}
    </span>
  );

  const titulo = (
    <span className="flex items-center gap-2 flex-wrap">
      <EyeOff className="w-4 h-4 text-[var(--honey-amber)]" />
      {b.title}
      {progreso}
    </span>
  );

  const botonSecundario =
    'rounded-lg px-3.5 py-2 text-[12px] text-white/60 ring-1 ring-white/10 hover:text-white/85 transition';
  const botonPrincipal =
    'rounded-lg px-4 py-2 text-[12px] font-medium transition disabled:opacity-35 disabled:cursor-not-allowed bg-[var(--honey-amber)] text-[var(--sobre-ambar)] hover:brightness-110';

  let pie;
  if (!item || item.terminada || error) {
    pie = (
      <div className="flex justify-end">
        <button onClick={onCerrar} className={botonSecundario}>
          {m.close}
        </button>
      </div>
    );
  } else if (resultado) {
    pie = (
      <div className="flex justify-end gap-2">
        <button onClick={onCerrar} className={botonSecundario}>
          {b.pause}
        </button>
        <button onClick={cargar} data-foco-inicial="" className={botonPrincipal}>
          {b.next}
        </button>
      </div>
    );
  } else {
    pie = (
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="text-[10.5px] text-white/40">{listo ? m.untouched : b.missing}</span>
        <div className="flex gap-2 ml-auto">
          <button onClick={onCerrar} className={botonSecundario}>
            {b.pause}
          </button>
          <button onClick={guardar} disabled={!listo || guardando} className={botonPrincipal}>
            {guardando ? b.saving : b.save}
          </button>
        </div>
      </div>
    );
  }

  return (
    <Modal abierto={abierto} onCerrar={onCerrar} titulo={titulo} pie={pie} opaco>
      {error && <div className="text-[12px] text-[var(--agent-coral)] mb-3">{error}</div>}

      {!item && !error && (
        <div className="flex flex-col gap-3 animate-pulse" aria-label={b.loading}>
          <div className="h-28 rounded-xl bg-white/[0.04]" />
          <div className="h-16 rounded-xl bg-white/[0.03]" />
          <div className="h-32 rounded-xl bg-white/[0.03]" />
        </div>
      )}

      {item?.terminada && (
        <div className="flex flex-col items-center text-center gap-3 py-8">
          <CheckCircle2 className="w-10 h-10 text-[var(--neural-teal)]" />
          <p className="text-[13px] text-white/75 max-w-sm leading-relaxed">{b.done(item.total)}</p>
        </div>
      )}

      {item && !item.terminada && item.evento && (
        <div className="flex flex-col gap-5">
          {!resultado && <p className="text-[12px] text-white/55 leading-relaxed">{b.intro}</p>}

          <Evento item={item} />

          {resultado ? (
            <Comparacion resultado={resultado} tacticName={tacticName} />
          ) : (
            <>
              <div>
                <div className="text-[13px] text-white/85">{m.severityQ}</div>
                <div className="text-[11px] text-white/45 mt-0.5 mb-2.5">
                  {b.range(nivel(item.piso ?? ''), nivel(item.techo ?? ''))}
                </div>
                <SelectorSeveridad
                  valor={severidad}
                  onElegir={setSeveridad}
                  piso={item.piso ?? ''}
                  techo={item.techo ?? ''}
                  rotulo={m.severityQ}
                />
              </div>

              <div>
                <div className="text-[13px] text-white/85 mb-2.5">{m.tacticQ}</div>
                <SelectorTactica
                  valor={tactica}
                  onElegir={setTactica}
                  rotulo={m.tacticQ}
                  tacticName={tacticName}
                />
              </div>

              <label className="flex flex-col gap-1.5">
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
            </>
          )}
        </div>
      )}
    </Modal>
  );
}

/** El evento tal como lo capturó el sensor, sin nada de lo que el motor concluyó sobre él. */
function Evento({ item }: { item: ItemACiegas }) {
  const { t } = useI18n();
  const b = t.triage.blind;
  const e = item.evento!;
  const datos = [e.sensor, e.categoria, e.accion, e.resultado, e.protocolo].filter(Boolean);
  return (
    <div className="rounded-xl bg-white/[0.03] ring-1 ring-white/[0.07] p-3.5 flex flex-col gap-2.5">
      <div className="rotulo">{b.event}</div>
      <div className="font-data text-[12px] text-white/80 break-all leading-relaxed">
        {e.resumen}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {datos.map((d, i) => (
          <span
            key={i}
            className="font-data text-[10px] rounded px-1.5 py-0.5 text-white/55 ring-1 ring-white/10"
          >
            {d}
          </span>
        ))}
        {e.momento && (
          <span className="font-data text-[10px] text-white/40 self-center ml-1">
            {fechaHora(e.momento)}
          </span>
        )}
      </div>
      <details className="group rounded-lg ring-1 ring-white/[0.07] bg-white/[0.02]">
        <summary className="flex items-center justify-between gap-2 cursor-pointer list-none px-3 py-2 text-[11.5px] text-white/65 hover:text-white/90">
          {b.attributes}
          <ChevronDown className="w-3.5 h-3.5 text-white/35 transition-transform group-open:rotate-180" />
        </summary>
        <div className="px-3 pb-3">
          {item.atributos ? (
            <dl className="grid grid-cols-[minmax(0,40%)_minmax(0,1fr)] gap-x-3 gap-y-1">
              {Object.entries(item.atributos).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="font-data text-[10px] text-white/40 truncate">{k}</dt>
                  <dd className="font-data text-[10px] text-white/75 break-all">
                    {Array.isArray(v) ? v.join(', ') : typeof v === 'number' ? n(v) : String(v)}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-[11px] text-white/50">{b.noEvent}</p>
          )}
        </div>
      </details>
    </div>
  );
}

/** Lo elegido al lado de lo del motor, renglón por renglón, con si coinciden o no. */
function Comparacion({
  resultado,
  tacticName,
}: {
  resultado: Revision;
  tacticName: (key: string) => string;
}) {
  const { t } = useI18n();
  const b = t.triage.blind;
  const motor = resultado.motor;
  const tactica = (k: string | null) => (
    <span
      className="text-[12px]"
      style={{ color: k ? tacticColor(k) : 'rgb(var(--tinta) / 0.45)' }}
    >
      {k ? tacticName(k) : t.triage.noTactic}
    </span>
  );
  const renglones = [
    {
      rotulo: b.severity,
      propio: <ChipSeveridad severidad={resultado.severidad} grande />,
      delMotor: <ChipSeveridad severidad={motor.severidad} grande />,
      coincide: resultado.severidad === motor.severidad,
    },
    {
      rotulo: b.tactic,
      propio: tactica(resultado.tactica_mitre),
      delMotor: tactica(motor.tactica_mitre),
      coincide: (resultado.tactica_mitre ?? null) === (motor.tactica_mitre ?? null),
    },
  ];
  return (
    <div className="section-in flex flex-col gap-3">
      <div className="rounded-xl ring-1 ring-white/[0.07] overflow-hidden">
        <div className="grid grid-cols-[5.5rem_minmax(0,1fr)_minmax(0,1fr)] gap-x-3 px-3.5 py-2 bg-white/[0.03] rotulo">
          <span />
          <span>{b.yours}</span>
          <span>{b.engine}</span>
        </div>
        {renglones.map((r) => (
          <div
            key={r.rotulo}
            className="grid grid-cols-[5.5rem_minmax(0,1fr)_minmax(0,1fr)] gap-x-3 items-center px-3.5 py-3 border-t border-white/5"
          >
            <span className="flex items-center gap-1.5 text-[11px] text-white/55">
              {r.coincide ? (
                <CheckCircle2
                  className="w-3.5 h-3.5 text-[var(--neural-teal)]"
                  aria-label={b.matches}
                />
              ) : (
                <CircleSlash
                  className="w-3.5 h-3.5 text-[var(--agent-coral)]"
                  aria-label={b.differs}
                />
              )}
              {r.rotulo}
            </span>
            <span>{r.propio}</span>
            <span>{r.delMotor}</span>
          </div>
        ))}
      </div>
      <p className="text-[11.5px] text-white/55">
        {b.recorded(resultado.veredicto === 'confirma')}
      </p>
    </div>
  );
}
