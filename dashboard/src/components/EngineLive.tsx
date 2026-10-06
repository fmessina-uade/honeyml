import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Brain, RotateCcw } from 'lucide-react';
import { api, type FilaDecision, type NodoDelGrafo, type ResumenTriaje } from '../lib/api';
import type { Llegada } from '../lib/useMotorEnVivo';
import Latido from './Latido';
import { dec, duracion, n } from '../lib/format';
import { useI18n } from '../lib/i18n';
import { useQuieto } from '../lib/useQuieto';
import { ChipSeveridad } from './triaje/comunes';
import { tacticColor } from './sections/SessionReplay';

type Paso = NodoDelGrafo | 'bus';

// Las estaciones de la vía, en el orden del grafo. Una decisión no siempre pasa por todas: la
// memoria y la falta de contexto saltan directo a persistencia, y la validación puede devolver la
// respuesta al modelo.
const ESTACIONES: Paso[] = [
  'bus',
  'memoria',
  'contexto',
  'historial',
  'inferencia',
  'validacion',
  'persistencia',
];

const COLOR: Record<Paso, string> = {
  bus: 'var(--ghost-slate)',
  memoria: 'var(--neural-teal)',
  contexto: 'var(--celeste)',
  historial: 'var(--violeta)',
  inferencia: 'var(--agent-coral)',
  validacion: 'var(--honey-amber)',
  persistencia: 'var(--motor-guardado)',
};

// Cuánto se muestra cada hecho antes de pasar al siguiente. No es la duración real de cada paso,
// que el motor no guarda: es el ritmo de lectura. Inferencia es la más larga porque es donde
// interviene el modelo, y es lo que el lector tiene que ver pasar.
const PAUSA: Record<Paso, number> = {
  bus: 900,
  memoria: 1000,
  contexto: 1000,
  historial: 950,
  inferencia: 2000,
  validacion: 1050,
  persistencia: 1200,
};
// Cuánto queda en pantalla la decisión terminada antes de la siguiente.
const RESPIRO_MS = 2600;
const MINUTOS_ACTIVO = 10;
const BITACORA = 6;

// El medidor de demora va en escala logarítmica de un segundo a una hora: una decisión copiada
// tarda segundos y una que esperó en el bus puede tardar horas, y las dos tienen que entrar.
const MARCAS_DEMORA: [number, string][] = [
  [1, '1 s'],
  [10, '10 s'],
  [60, '1 min'],
  [600, '10 min'],
  [3600, '1 h'],
];
const enMedidor = (s: number) =>
  Math.min(Math.max(Math.log10(Math.max(s, 1)) / Math.log10(3600), 0), 1);

interface EnCola {
  fila: FilaDecision;
  repeticion: boolean;
}

interface Hecho {
  clave: string;
  paso: Paso;
  titular: string;
  texto: string;
  dato: string[];
  rechazo?: boolean;
}

const hora = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString(undefined, { hour12: false }) : null;

/**
 * El motor de triaje trabajando, como una vía con sus estaciones.
 *
 * Cada decisión que llega recorre la vía en el orden en que la resolvió el motor: entró del bus,
 * buscó la conducta en el repertorio, juntó el contexto, le pidió la decisión al modelo, la
 * validación la aceptó o la devolvió, y quedó guardada. Un salto de la memoria o de la falta de
 * contexto se dibuja como un arco por encima de las estaciones que no tocó, y una devolución como
 * un arco que vuelve al modelo. Lo que dice cada paso sale de lo que el motor guardó de esa
 * decisión, así la vía no muestra nada que no haya pasado. Las horas que aparecen son las únicas
 * que se conocen: la del evento y la de la decisión.
 *
 * Las decisiones llegan del sondeo de la sección, el mismo que actualiza los números y el listado.
 * Cuando no llega nada nuevo, se puede repetir lo último que decidió, y el panel lo dice.
 */
export default function EngineLive({
  resumen,
  recientes,
  llegada,
  error,
  tacticName,
  onElegir,
}: {
  resumen: ResumenTriaje;
  recientes: FilaDecision[];
  llegada: Llegada;
  error: string | null;
  tacticName: (key: string) => string;
  onElegir: (docId: string) => void;
}) {
  const { t } = useI18n();
  const e = t.triage.engine;
  const l = e.timeline;
  // Los textos se leen por referencia dentro del recorrido: cambiar de idioma no tiene por qué
  // reiniciar una decisión que está a mitad de camino.
  const textos = useRef(e);
  textos.current = e;
  const quieto = useQuieto();
  const quietoRef = useRef(quieto);
  quietoRef.current = quieto;

  const [actual, setActual] = useState<EnCola | null>(null);
  // La última que se mostró. Queda en pantalla hasta que empieza la siguiente, así la vía no se
  // vacía entre una decisión y otra.
  const [mostrada, setMostrada] = useState<EnCola | null>(null);
  const [visibles, setVisibles] = useState(0);
  const [pensamiento, setPensamiento] = useState('');
  const [palabras, setPalabras] = useState(0);
  const [ahora, setAhora] = useState(() => Date.now());

  const cola = useRef<EnCola[]>([]);
  const justificacion = useRef<Record<string, string>>({});
  // La decisión en curso vive también en una referencia: sacar de la cola es un efecto, y no puede
  // ir dentro de la función que actualiza el estado, que React puede ejecutar dos veces.
  const enMarcha = useRef<EnCola | null>(null);

  const siguiente = useCallback(() => {
    const proxima = cola.current.shift() ?? null;
    enMarcha.current = proxima;
    setActual(proxima);
  }, []);

  const encolar = useCallback(
    (filas: FilaDecision[], repeticion: boolean) => {
      // De la más vieja a la más nueva, que es el orden en que las decidió el motor. Con la pestaña
      // oculta se pueden juntar muchas: se conservan las últimas.
      cola.current.push(...[...filas].reverse().map((fila) => ({ fila, repeticion })));
      cola.current = cola.current.slice(-30);
      if (!enMarcha.current) siguiente();
    },
    [siguiente],
  );

  // Al abrir la sección se repite la última, así la vía no arranca vacía. Se la marca como
  // repetición para que el panel no la presente como recién llegada.
  const arrancado = useRef(false);
  useEffect(() => {
    if (arrancado.current || !recientes.length) return;
    arrancado.current = true;
    encolar(recientes.slice(0, 1), true);
  }, [recientes, encolar]);

  // Lo que el sondeo trae de nuevo entra a la cola.
  useEffect(() => {
    if (llegada.serie > 0) encolar(llegada.filas, false);
  }, [llegada, encolar]);

  useEffect(() => {
    const reloj = window.setInterval(() => setAhora(Date.now()), 1000);
    return () => window.clearInterval(reloj);
  }, []);

  const hechosDe = useCallback((fila: FilaDecision): Hecho[] => {
    const x = textos.current.timeline;
    const h = x.heads;
    const m = x.marks;
    const hechos: Hecho[] = [
      {
        clave: 'bus',
        paso: 'bus',
        titular: h.received,
        texto: x.receivedFact(fila.sensor ?? '—', fila.protocolo ?? '—', fila.categoria ?? '—'),
        dato: [hora(fila.momento)].filter((d): d is string => Boolean(d)),
      },
    ];
    let pedidos = 0;
    let devoluciones = 0;
    fila.camino.forEach((nodo, i) => {
      const clave = `${nodo}-${i}`;
      if (nodo === 'memoria') {
        hechos.push({
          clave,
          paso: nodo,
          titular: fila.copiada ? h.known : h.fresh,
          texto: fila.copiada ? x.memoryHit : x.memoryMiss,
          dato: [fila.copiada ? m.known : m.fresh],
        });
      } else if (nodo === 'contexto') {
        const sinContexto = fila.motivo_de_corte === 'sin_contexto';
        const fallidas = fila.consultas_fallidas.length;
        hechos.push({
          clave,
          paso: nodo,
          titular: sinContexto ? h.noContext : h.context,
          texto: sinContexto
            ? textos.current.noContext
            : fallidas
              ? x.contextFailed(fila.consultas_fallidas.join(', '))
              : x.context,
          dato: [sinContexto ? m.noContext : fallidas ? m.failed(fallidas) : m.context],
        });
      } else if (nodo === 'historial') {
        hechos.push({ clave, paso: nodo, titular: h.history, texto: x.history, dato: [m.history] });
      } else if (nodo === 'inferencia') {
        pedidos += 1;
        const ultimo = !fila.camino.slice(i + 1).includes('inferencia');
        hechos.push({
          clave,
          paso: nodo,
          titular: pedidos === 1 ? h.inference : h.retry,
          texto: pedidos === 1 ? x.inference(fila.modelo ?? '—') : x.inferenceRetry,
          dato: [
            pedidos > 1 ? m.asks(pedidos) : null,
            ultimo && fila.segundos != null ? `${dec(fila.segundos, 1)} s` : null,
          ].filter((d): d is string => Boolean(d)),
        });
      } else if (nodo === 'validacion') {
        const rechazo = fila.camino[i + 1] === 'inferencia';
        if (rechazo) devoluciones += 1;
        hechos.push({
          clave,
          paso: nodo,
          titular: rechazo ? h.rejected : h.accepted,
          texto: rechazo ? x.rejected : x.accepted,
          dato: [
            rechazo ? m.rejected : m.accepted,
            !rechazo && devoluciones ? m.returned(devoluciones) : null,
          ].filter((d): d is string => Boolean(d)),
          rechazo,
        });
      } else {
        hechos.push({
          clave,
          paso: nodo,
          titular: h.saved,
          texto: '',
          dato: [hora(fila.decidida)].filter((d): d is string => Boolean(d)),
        });
      }
    });
    return hechos;
  }, []);

  // La decisión en curso, un hecho por vez.
  useEffect(() => {
    if (!actual) return;
    setMostrada(actual);
    const { fila } = actual;
    const hechos = hechosDe(fila);

    if (fila.camino.includes('inferencia') && !justificacion.current[fila.doc_id]) {
      api
        .decision(fila.doc_id)
        .then((d) => {
          justificacion.current[fila.doc_id] = d.decision.decision.justificacion ?? '';
          if (enMarcha.current?.fila.doc_id === fila.doc_id) {
            setPensamiento(justificacion.current[fila.doc_id] || textos.current.reasoning);
          }
        })
        .catch(() => undefined);
    }
    setPensamiento(
      fila.copiada
        ? textos.current.copied
        : fila.motivo_de_corte === 'sin_contexto'
          ? textos.current.noContext
          : justificacion.current[fila.doc_id] || textos.current.reading,
    );

    if (quietoRef.current) {
      setVisibles(hechos.length);
      const espera = window.setTimeout(siguiente, 1500);
      return () => window.clearTimeout(espera);
    }

    // Con varias esperando, el ritmo se apura para no quedar atrás del motor. La repetición no: la
    // pidió alguien que quiere ver el ciclo, y no hay nada que alcanzar.
    const pendientes = cola.current.length;
    const rapidez = actual.repeticion ? 1 : pendientes > 6 ? 4 : pendientes > 2 ? 2 : 1;
    let k = 0;
    let reloj = 0;
    const avanzar = () => {
      k += 1;
      setVisibles(k);
      if (k < hechos.length) {
        reloj = window.setTimeout(avanzar, PAUSA[hechos[k - 1].paso] / rapidez);
      } else {
        reloj = window.setTimeout(siguiente, RESPIRO_MS / rapidez);
      }
    };
    setVisibles(0);
    reloj = window.setTimeout(avanzar, 120);
    return () => window.clearTimeout(reloj);
  }, [actual, siguiente, hechosDe]);

  // El razonamiento aparece de a una palabra, como sale de un modelo de lenguaje.
  useEffect(() => {
    const cuantas = pensamiento.split(/(\s+)/).length;
    if (quieto) {
      setPalabras(cuantas);
      return;
    }
    setPalabras(0);
    let k = 0;
    const id = window.setInterval(() => {
      k += 2;
      setPalabras(k);
      if (k >= cuantas) window.clearInterval(id);
    }, 55);
    return () => window.clearInterval(id);
  }, [pensamiento, quieto]);

  // La repetición mezcla lo último que decidió con las últimas decisiones razonadas. Casi todo
  // sale por memoria, y sin mezclar la repetición mostraría un solo camino de los tres.
  const repetir = () => {
    api
      .decisiones({ estado: 'todas', desde: 0, tamano: 2, orden: 'decision', razonadas: true })
      .catch(() => ({ items: [] as FilaDecision[] }))
      .then((razonadas) => {
        const juntas = new Map<string, FilaDecision>();
        [...recientes.slice(0, 4), ...razonadas.items].forEach((d) => juntas.set(d.doc_id, d));
        const ordenadas = [...juntas.values()].sort((a, b) =>
          (b.decidida ?? '').localeCompare(a.decidida ?? ''),
        );
        encolar(ordenadas, true);
      });
  };

  const ultima = recientes[0]?.decidida ?? resumen.actividad.ultima;
  const hace = ultima ? Math.max(0, (ahora - new Date(ultima).getTime()) / 1000) : null;
  const activo = hace !== null && hace < MINUTOS_ACTIVO * 60;
  const enPantalla = actual ?? mostrada;
  const fila = enPantalla?.fila;
  const hechos = fila ? hechosDe(fila) : [];
  const terminada = fila ? visibles >= hechos.length : false;
  const foco = fila ? hechos[Math.min(Math.max(visibles - 1, 0), hechos.length - 1)] : null;
  const pasoActivo = fila && !terminada ? (foco?.paso ?? null) : null;
  const pensando = pasoActivo === 'inferencia' && !quieto;
  const partes = pensamiento.split(/(\s+)/);
  const guardada = terminada && Boolean(fila?.camino.includes('persistencia'));

  const camino = !fila
    ? null
    : fila.copiada
      ? e.paths.memory
      : fila.motivo_de_corte === 'sin_contexto'
        ? e.paths.noContext
        : fila.rechazos
          ? e.paths.retry
          : e.paths.full;

  const demora =
    fila?.momento && fila.decidida && !fila.retriaje
      ? (new Date(fila.decidida).getTime() - new Date(fila.momento).getTime()) / 1000
      : null;
  const mediana = resumen.conclusion.mediana_s;

  const cifras: [string, string][] = [
    [n(resumen.actividad.ultima_hora), e.lastHour],
    [n(resumen.actividad.copiadas_ultima_hora), e.byMemory],
  ];
  if (mediana !== null) cifras.push([duracion(mediana), e.toConclusion]);

  const nombre = (p: Paso) => (p === 'bus' ? l.bus : e.nodes[p].name);

  return (
    <section className="motor escenario relative overflow-hidden">
      <div aria-hidden className="escenario-luz" data-pensando={pensando ? 'si' : 'no'} />

      <div className="relative px-5 py-5 sm:px-8 sm:py-6 flex flex-col">
        {/* Estado del agente y de lo que se está mostrando */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="relative flex w-2.5 h-2.5">
              {activo && (
                <span className="absolute inline-flex h-full w-full rounded-full bg-[#ff6b35] opacity-60 animate-ping" />
              )}
              <span
                className="relative inline-flex w-2.5 h-2.5 rounded-full"
                style={{ background: activo ? 'var(--agent-coral)' : 'var(--motor-apagado)' }}
              />
            </span>
            <span className="geist text-[15px] font-medium tracking-tight text-white">
              {activo ? e.active : e.idle}
            </span>
            {hace !== null && (
              <span className="font-data text-[11px] text-white/45">
                {e.lastAgo(duracion(hace))}
              </span>
            )}
          </div>
          {enPantalla?.repeticion && (
            <span className="text-[11px] text-white/45">{e.replaying}</span>
          )}
        </div>

        {/* Lo que pasa ahora, lo que razonó el modelo y la vía. En una columna la vía va antes del
            panel, pegada a la frase que la explica. */}
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-x-10 gap-y-6 mt-5 lg:mt-6">
          <div className="order-1 min-w-0 flex flex-col justify-center">
            {fila && foco ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rotulo mr-1">{terminada ? l.last : l.current}</span>
                  <span className="metal metal-chica">{camino}</span>
                  <span className="metal metal-chica font-data">
                    {l.run(fila.doc_id.slice(0, 6))}
                  </span>
                </div>
                <Frase
                  key={fila.doc_id + foco.clave + String(enPantalla?.repeticion)}
                  texto={foco.titular}
                />
                <div className="min-h-[44px] mt-2.5 max-w-[560px]">
                  {foco.paso === 'persistencia' ? (
                    <div className="motor-sube flex flex-wrap items-center gap-3">
                      <ChipSeveridad severidad={fila.severidad} grande />
                      <span
                        className="geist text-[16px] tracking-tight"
                        style={{
                          color: fila.tactica_mitre
                            ? tacticColor(fila.tactica_mitre)
                            : 'rgb(var(--tinta) / 0.5)',
                        }}
                      >
                        {fila.tactica_mitre ? tacticName(fila.tactica_mitre) : t.triage.noTactic}
                      </span>
                    </div>
                  ) : (
                    <p
                      key={foco.clave}
                      className="motor-sube text-[14px] leading-relaxed text-white/60"
                    >
                      {foco.texto}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => onElegir(fila.doc_id)}
                  title={e.open}
                  className="group flex items-center gap-2 max-w-full min-w-0 text-left mt-1"
                >
                  <span className="font-data text-[11.5px] text-white/45 truncate group-hover:text-white/80 transition">
                    {fila.resumen}
                  </span>
                  <span className="shrink-0 text-[11px] text-[var(--motor-acento)] opacity-0 group-hover:opacity-100 transition">
                    {e.open}
                  </span>
                </button>
              </>
            ) : (
              <p className="text-[13px] text-white/45">{error ?? e.waiting}</p>
            )}
          </div>

          {/* El panel de vidrio: el razonamiento y, al guardarse, cuánto tardó desde el evento */}
          <aside className="order-3 lg:order-2 vidrio p-4 sm:p-5 flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <span className="geist text-[15.5px] font-medium tracking-tight text-white">
                  {l.reasoned}
                </span>
                <span className="punto-vivo" data-pensando={pensando ? 'si' : 'no'} />
              </div>
              <span className="circulo-luz" data-pensando={pensando ? 'si' : 'no'}>
                <Brain className="w-4 h-4" />
              </span>
            </div>
            <p className="text-[13px] text-white/75 leading-relaxed flex-1">
              {fila ? (
                <>
                  {partes.slice(0, palabras).map((parte, k) => (
                    <span key={k} className="motor-token">
                      {parte}
                    </span>
                  ))}
                  <span className="terminal-cursor inline-block w-1.5 h-3.5 ml-0.5 align-middle rounded-sm bg-[var(--agent-coral)]" />
                </>
              ) : (
                <span className="text-white/45">{e.waiting}</span>
              )}
            </p>

            <div>
              <div className="flex items-baseline justify-between gap-2">
                <span className="rotulo">{e.toConclusion}</span>
                {guardada && demora !== null && (
                  <span className="font-data text-[11px] text-white/80 whitespace-nowrap">
                    {l.savedAfter(duracion(demora))}
                  </span>
                )}
              </div>
              <div className="relative mt-3 h-4 text-[10px] font-data text-white/40">
                {MARCAS_DEMORA.map(([s, rotulo], i) => (
                  <span
                    key={rotulo}
                    className="absolute top-0 whitespace-nowrap"
                    style={{
                      left: `${enMedidor(s) * 100}%`,
                      transform:
                        i === 0
                          ? 'none'
                          : i === MARCAS_DEMORA.length - 1
                            ? 'translateX(-100%)'
                            : 'translateX(-50%)',
                    }}
                  >
                    {rotulo}
                  </span>
                ))}
              </div>
              <div className="medidor mt-1.5">
                {guardada && demora !== null && (
                  <i
                    key={fila?.doc_id}
                    style={{ width: `${Math.max(enMedidor(demora) * 100, 2)}%` }}
                  />
                )}
                {mediana !== null && <b style={{ left: `${enMedidor(mediana) * 100}%` }} />}
              </div>
              <p className="text-[10.5px] text-white/40 mt-2 min-h-[15px]">
                {!guardada
                  ? l.meterWaiting
                  : demora === null
                    ? l.meterNone
                    : mediana !== null
                      ? l.meterMedian(duracion(mediana))
                      : ''}
              </p>
            </div>
          </aside>

          {/* La vía: por qué estaciones pasó la decisión */}
          <div className="order-2 lg:order-3 lg:col-span-2 min-w-0">
            {fila && (
              <Via
                key={fila.doc_id + String(enPantalla?.repeticion)}
                hechos={hechos}
                visibles={visibles}
                activo={pasoActivo}
                nombre={nombre}
                descripcion={(p) => (p === 'bus' ? '' : e.nodes[p].what)}
                enCurso={l.inProgress}
              />
            )}
          </div>
        </div>

        {/* Las últimas ejecuciones y el pulso de la hora */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12 mt-8">
          <div className="min-w-0">
            <span className="rotulo">{l.log}</span>
            <p className="text-[11px] text-white/40 mt-1">{l.logHint}</p>
            <ul className="mt-3 flex flex-col">
              {recientes.slice(0, BITACORA).map((d) => (
                <li key={d.doc_id} className="border-t border-white/[0.06] first:border-t-0">
                  <button
                    onClick={() => onElegir(d.doc_id)}
                    data-actual={fila?.doc_id === d.doc_id ? 'si' : undefined}
                    className="bitacora-fila w-full grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-3 px-2 py-2.5 text-left"
                  >
                    <span className="font-data text-[10.5px] text-white/40">
                      {hora(d.decidida) ?? '—'}
                    </span>
                    <span className="font-data text-[11px] text-white/70 truncate">
                      {d.resumen}
                    </span>
                    <Firma fila={d} />
                    <ChipSeveridad severidad={d.severidad} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div className="min-w-0">
            {resumen.actividad.por_minuto?.length ? (
              <Latido serie={resumen.actividad.por_minuto} alto={92} />
            ) : (
              <div className="text-[11px] text-white/40">{e.pulseMissing}</div>
            )}
          </div>
        </div>

        {/* Las cifras de la hora, finas y grandes, y la repetición */}
        <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-5 mt-7 pt-6 border-t border-white/[0.07]">
          <div className="flex flex-wrap items-end gap-x-4 gap-y-4">
            {cifras.map(([valor, texto], i) => (
              <div key={texto} className="flex items-end gap-4">
                {i > 0 && <span className="barra-oblicua" aria-hidden />}
                <div className="flex items-end gap-3">
                  <span className="cifra-fina">{valor}</span>
                  <span className="text-[12px] leading-snug text-white/55 max-w-[9.5em] pb-1">
                    {texto}
                  </span>
                </div>
              </div>
            ))}
          </div>
          <button onClick={repetir} disabled={!recientes.length} className="pildora-perilla">
            <span>{e.replay}</span>
            <span className="perilla" aria-hidden>
              <RotateCcw className="w-4 h-4" />
            </span>
          </button>
        </div>
      </div>
    </section>
  );
}

/** Lo que está pasando, en grande: cada palabra sube detrás de su máscara y la última va en ámbar. */
function Frase({ texto }: { texto: string }) {
  const palabras = texto.split(' ');
  const ultima = palabras.length - 1;
  return (
    <p className="motor-frase mt-2.5" aria-live="polite" aria-label={texto}>
      {palabras.map((p, i) => (
        <span key={i} aria-hidden>
          <span className="titular-mascara">
            <span
              className={i === ultima ? 'motor-frase-fin' : undefined}
              style={{ '--d': `${i * 0.06}s` } as React.CSSProperties}
            >
              {p}
            </span>
          </span>
          {i < ultima && ' '}
        </span>
      ))}
    </p>
  );
}

/**
 * La vía con sus siete estaciones. Las estaciones van como elementos debajo del trazo y no dentro
 * del dibujo, así el texto no se deforma con el ancho; el trazo se dibuja con el ancho medido.
 */
function Via({
  hechos,
  visibles,
  activo,
  nombre,
  descripcion,
  enCurso,
}: {
  hechos: Hecho[];
  visibles: number;
  activo: Paso | null;
  nombre: (p: Paso) => string;
  descripcion: (p: Paso) => string;
  enCurso: string;
}) {
  const caja = useRef<HTMLDivElement>(null);
  const [ancho, setAncho] = useState(0);
  useLayoutEffect(() => {
    const el = caja.current;
    if (!el) return;
    const medir = () => setAncho(el.clientWidth);
    medir();
    const obs = new ResizeObserver(medir);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const ALTO = 62;
  const LINEA = 55;
  const tramo = ancho / ESTACIONES.length;
  const xDe = (p: Paso) => (ESTACIONES.indexOf(p) + 0.5) * tramo;
  const mostrados = hechos.slice(0, visibles);
  const recorridas = new Set(mostrados.map((h) => h.paso));
  const delCamino = new Set(hechos.map((h) => h.paso));
  const terminada = visibles >= hechos.length;

  // Un tramo por cada par de hechos seguidos: recto entre estaciones vecinas, un arco por encima
  // cuando salta estaciones, y un arco en rojo cuando la validación vuelve al modelo.
  const tramos = mostrados.slice(1).map((h, j) => {
    const desde = mostrados[j].paso;
    const a = xDe(desde);
    const b = xDe(h.paso);
    const salto = Math.abs(ESTACIONES.indexOf(h.paso) - ESTACIONES.indexOf(desde));
    const vuelta = b < a;
    const alto = vuelta ? 26 : salto > 1 ? Math.min(18 + salto * 8, LINEA - 4) : 0;
    const d = alto
      ? `M ${a} ${LINEA} C ${a} ${LINEA - alto}, ${b} ${LINEA - alto}, ${b} ${LINEA}`
      : `M ${a} ${LINEA} L ${b} ${LINEA}`;
    return {
      clave: `${j}-${desde}-${h.paso}`,
      d,
      color: vuelta ? 'var(--critico)' : salto > 1 ? COLOR[desde] : 'rgb(var(--tinta) / 0.7)',
      punteado: vuelta || salto > 1,
    };
  });

  return (
    <div ref={caja} className="via" role="list">
      <svg width={ancho} height={ALTO} className="block overflow-visible" aria-hidden>
        {ancho > 0 && (
          <>
            <line
              x1={xDe('bus')}
              x2={xDe('persistencia')}
              y1={LINEA}
              y2={LINEA}
              className="via-base"
            />
            {tramos.map((tr) => (
              <path
                key={tr.clave}
                d={tr.d}
                pathLength={1}
                className="via-tramo"
                data-punteado={tr.punteado ? 'si' : undefined}
                style={{ stroke: tr.color }}
              />
            ))}
          </>
        )}
      </svg>
      <div
        className="grid -mt-[15px]"
        style={{ gridTemplateColumns: `repeat(${ESTACIONES.length}, minmax(0, 1fr))` }}
      >
        {ESTACIONES.map((p) => {
          const propios = mostrados.filter((h) => h.paso === p);
          const ultimo = propios[propios.length - 1];
          const estado =
            activo === p
              ? 'activa'
              : recorridas.has(p)
                ? 'recorrida'
                : terminada || !delCamino.has(p)
                  ? 'salteada'
                  : 'pendiente';
          return (
            <div
              key={p}
              role="listitem"
              className="estacion"
              data-estado={estado}
              data-rechazo={ultimo?.rechazo ? 'si' : undefined}
              title={descripcion(p) || undefined}
              style={{ '--tono': COLOR[p] } as React.CSSProperties}
            >
              <span className="estacion-marca" aria-hidden />
              <span className="estacion-nombre geist">{nombre(p)}</span>
              <span className="estacion-dato font-data">
                {estado === 'activa' && !ultimo?.dato.length
                  ? enCurso
                  : (ultimo?.dato ?? []).map((d) => <span key={d}>{d}</span>)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** La firma del camino en la bitácora: una raya por estación, encendida si la decisión pasó. */
function Firma({ fila }: { fila: FilaDecision }) {
  const devuelta = fila.camino.some(
    (p, i) => p === 'validacion' && fila.camino[i + 1] === 'inferencia',
  );
  const pasos = new Set<Paso>(['bus', ...fila.camino]);
  return (
    <span className="firma hidden sm:flex" aria-hidden>
      {ESTACIONES.map((p) => (
        <i
          key={p}
          style={{
            background: !pasos.has(p)
              ? 'rgb(var(--tinta) / 0.1)'
              : p === 'validacion' && devuelta
                ? 'var(--critico)'
                : COLOR[p],
          }}
        />
      ))}
    </span>
  );
}
