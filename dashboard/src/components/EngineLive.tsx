import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Brain,
  Database,
  History,
  RotateCcw,
  Save,
  Search,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react';
import { api, type FilaDecision, type NodoDelGrafo, type ResumenTriaje } from '../lib/api';
import { dec, duracion, hora, n } from '../lib/format';
import { useI18n } from '../lib/i18n';
import { useQuieto } from '../lib/useQuieto';

// El grafo del motor sobre un lienzo de 1000 por 330. Los nodos siguen una curva en el orden en que
// los recorre un evento, y las tres aristas largas son lo que lo vuelve una máquina de estados y no
// una cadena: los dos atajos a persistencia y la vuelta de validación a inferencia.
const ANCHO = 1000;
const ALTO = 330;
const R = 32;

interface Nodo {
  id: NodoDelGrafo;
  x: number;
  y: number;
  icono: LucideIcon;
  color: string;
}

const NODOS: Nodo[] = [
  { id: 'memoria', x: 95, y: 205, icono: Database, color: '#00b894' },
  { id: 'contexto', x: 255, y: 168, icono: Search, color: '#94a3b8' },
  { id: 'historial', x: 415, y: 150, icono: History, color: '#94a3b8' },
  { id: 'inferencia', x: 585, y: 150, icono: Brain, color: '#ff6b35' },
  { id: 'validacion', x: 745, y: 168, icono: ShieldCheck, color: '#d4860a' },
  { id: 'persistencia', x: 905, y: 205, icono: Save, color: '#e2e8f0' },
];
const P = Object.fromEntries(NODOS.map((nodo) => [nodo.id, nodo])) as Record<NodoDelGrafo, Nodo>;

// Los colores del modelo de lenguaje. Aparecen solo sobre inferencia, y solo cuando una decisión
// pasó de verdad por el modelo: así el lector distingue a simple vista cuándo interviene.
const IRIDISCENTE = ['#ff6b35', '#f472b6', '#a78bfa', '#38bdf8', '#00b894'];

const curva = (a: NodoDelGrafo, b: NodoDelGrafo) => {
  const x1 = P[a].x + R * 0.9;
  const x2 = P[b].x - R * 0.9;
  return `M ${x1} ${P[a].y} C ${x1 + 48} ${P[a].y}, ${x2 - 48} ${P[b].y}, ${x2} ${P[b].y}`;
};

// Cada arista se nombra por sus dos extremos, en el sentido en que la recorre un evento.
const ARISTAS: Record<string, string> = {
  'memoria>contexto': curva('memoria', 'contexto'),
  'contexto>historial': curva('contexto', 'historial'),
  'historial>inferencia': curva('historial', 'inferencia'),
  'inferencia>validacion': curva('inferencia', 'validacion'),
  'validacion>persistencia': curva('validacion', 'persistencia'),
  'memoria>persistencia': 'M 95 173 C 240 -30, 760 -30, 905 173',
  'contexto>persistencia': 'M 283 184 C 300 320, 760 320, 877 221',
  'validacion>inferencia': 'M 745 136 C 735 78, 595 70, 585 118',
};
const LARGAS = new Set(['memoria>persistencia', 'contexto>persistencia', 'validacion>inferencia']);

// Por dónde le llega el contexto al modelo mientras razona. No son aristas del grafo: se dibujan
// solo en ese momento, para que se vea que lo que juntaron contexto e historial entra a inferencia.
const SINAPSIS = ['M 255 200 C 300 262, 500 240, 557 166', 'M 443 166 C 480 206, 520 206, 557 166'];

// Cuánto se detiene el recorrido en cada nodo. Inferencia es la más larga porque es donde el modelo
// razona, y es lo que el lector tiene que ver pasar.
const PAUSA: Record<NodoDelGrafo, number> = {
  memoria: 420,
  contexto: 320,
  historial: 320,
  inferencia: 1500,
  validacion: 420,
  persistencia: 800,
};
const VELOCIDAD = 0.42; // unidades del lienzo por milisegundo
const ESTELA = 70;

const INTERVALO_MS = 5000;
const VENTANA = 30;
const MINUTOS_ACTIVO = 10;

const SEVERITY_COLOR: Record<string, string> = {
  informativo: '#94a3b8',
  bajo: '#00b894',
  medio: '#d4860a',
  alto: '#ff6b35',
  critico: '#ef4444',
};

type Paso =
  { tipo: 'nodo'; nodo: NodoDelGrafo; ms: number } | { tipo: 'arista'; arista: string; ms: number };

interface EnCola {
  fila: FilaDecision;
  repeticion: boolean;
}

interface Onda {
  clave: number;
  nodo: NodoDelGrafo;
  color: string;
}

const hexagono = (cx: number, cy: number, r: number) =>
  Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 3) * i - Math.PI / 2;
    return `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`;
  }).join(' ');

// Una estrella de cuatro puntas, el destello que acompaña al modelo mientras razona.
const estrella = (cx: number, cy: number, r: number) => {
  const c = r * 0.28;
  return [
    `M ${cx} ${cy - r}`,
    `Q ${cx + c} ${cy - c} ${cx + r} ${cy}`,
    `Q ${cx + c} ${cy + c} ${cx} ${cy + r}`,
    `Q ${cx - c} ${cy + c} ${cx - r} ${cy}`,
    `Q ${cx - c} ${cy - c} ${cx} ${cy - r} Z`,
  ].join(' ');
};

function aristasDe(camino: NodoDelGrafo[]): string[] {
  return camino.slice(1).map((nodo, i) => `${camino[i]}>${nodo}`);
}

const idDe = (clave: string) => `motor-${clave.replace('>', '-')}`;

/**
 * El motor de triaje trabajando: cada decisión que toma recorre en pantalla el camino que siguió
 * por el grafo.
 *
 * Lo que se dibuja no es una ilustración sino lo que el motor guardó. La API deduce el camino de
 * cada decisión (una copia del repertorio salió por el atajo de memoria, una con reproches dio
 * vueltas entre inferencia y validación) y este componente lo reproduce en el mismo orden. Cuando
 * no llega nada nuevo, se puede repetir lo último que decidió, y el panel lo dice.
 */
export default function EngineLive({
  resumen,
  tacticName,
  onElegir,
}: {
  resumen: ResumenTriaje;
  tacticName: (key: string) => string;
  onElegir: (docId: string) => void;
}) {
  const { t } = useI18n();
  const e = t.triage.engine;
  // Los textos se leen por referencia dentro del recorrido: cambiar de idioma no tiene por qué
  // reiniciar una decisión que está a mitad de camino.
  const textos = useRef(e);
  textos.current = e;
  const quieto = useQuieto();
  const quietoRef = useRef(quieto);
  quietoRef.current = quieto;

  const [recientes, setRecientes] = useState<FilaDecision[]>([]);
  const [actual, setActual] = useState<EnCola | null>(null);
  // La última que recorrió el grafo. Queda en pantalla hasta que empieza la siguiente, así la
  // tarjeta del agente no se vacía entre una decisión y otra.
  const [mostrada, setMostrada] = useState<EnCola | null>(null);
  const [nodoActivo, setNodoActivo] = useState<NodoDelGrafo | null>(null);
  const [recorridas, setRecorridas] = useState<Set<string>>(new Set());
  const [ondas, setOndas] = useState<Onda[]>([]);
  const [resultado, setResultado] = useState<FilaDecision | null>(null);
  const [pensamiento, setPensamiento] = useState('');
  const [palabras, setPalabras] = useState(0);
  const [ahora, setAhora] = useState(() => Date.now());
  const [error, setError] = useState<string | null>(null);

  const conocidas = useRef<Set<string>>(new Set());
  const cola = useRef<EnCola[]>([]);
  const trazos = useRef<Record<string, SVGPathElement | null>>({});
  const cabeza = useRef<SVGGElement | null>(null);
  const estela = useRef<SVGPathElement | null>(null);
  const estelaBrillo = useRef<SVGPathElement | null>(null);
  const justificacion = useRef<Record<string, string>>({});
  const contadorDeOndas = useRef(0);

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

  const ondear = useCallback((nodo: NodoDelGrafo, color: string) => {
    contadorDeOndas.current += 1;
    const clave = contadorDeOndas.current;
    setOndas((o) => [...o.slice(-5), { clave, nodo, color }]);
  }, []);

  // Sondeo del motor: lo que decidió desde la última vez entra a la cola del recorrido.
  useEffect(() => {
    let vivo = true;
    const traer = (primera: boolean) =>
      api
        .decisiones({ estado: 'todas', desde: 0, tamano: VENTANA, orden: 'decision' })
        .then((l) => {
          if (!vivo) return;
          setError(null);
          setRecientes(l.items);
          const nuevas = l.items.filter((d) => !conocidas.current.has(d.doc_id));
          nuevas.forEach((d) => conocidas.current.add(d.doc_id));
          // Al abrir la sección se repite la última, así el grafo no arranca quieto. Se la marca
          // como repetición para que el panel no la presente como recién llegada.
          if (primera) encolar(l.items.slice(0, 1), true);
          else if (nuevas.length) encolar(nuevas, false);
        })
        .catch((err) => vivo && setError(String(err.message ?? err)));
    traer(true);
    const id = window.setInterval(() => traer(false), INTERVALO_MS);
    const reloj = window.setInterval(() => setAhora(Date.now()), 1000);
    return () => {
      vivo = false;
      window.clearInterval(id);
      window.clearInterval(reloj);
    };
  }, [encolar]);

  // El recorrido de la decisión en curso, paso a paso.
  useEffect(() => {
    if (!actual) return;
    setMostrada(actual);
    const { fila } = actual;
    const camino = fila.camino;
    setResultado(null);
    setRecorridas(new Set());

    if (camino.includes('inferencia') && !justificacion.current[fila.doc_id]) {
      api
        .decision(fila.doc_id)
        .then((d) => {
          justificacion.current[fila.doc_id] = d.decision.decision.justificacion ?? '';
        })
        .catch(() => undefined);
    }
    const textoDelAgente = () =>
      fila.copiada
        ? textos.current.copied
        : fila.motivo_de_corte === 'sin_contexto'
          ? textos.current.noContext
          : justificacion.current[fila.doc_id] || textos.current.reasoning;
    // Mientras el recorrido atraviesa contexto e historial, el agente todavía está juntando datos.
    setPensamiento(camino.includes('inferencia') ? textos.current.reading : textoDelAgente());

    if (quietoRef.current) {
      setNodoActivo(null);
      setRecorridas(new Set(aristasDe(camino)));
      setResultado(fila);
      setPensamiento(textoDelAgente());
      const espera = window.setTimeout(siguiente, 1500);
      return () => window.clearTimeout(espera);
    }

    const pasos: Paso[] = [{ tipo: 'nodo', nodo: camino[0], ms: PAUSA[camino[0]] }];
    aristasDe(camino).forEach((arista, i) => {
      const largo = trazos.current[arista]?.getTotalLength() ?? 160;
      pasos.push({ tipo: 'arista', arista, ms: largo / VELOCIDAD });
      pasos.push({ tipo: 'nodo', nodo: camino[i + 1], ms: PAUSA[camino[i + 1]] });
    });
    // Con varias esperando, el recorrido se apura para no quedar atrás del motor. La repetición no:
    // la pidió alguien que quiere ver el ciclo, y no hay nada que alcanzar.
    const pendientes = cola.current.length;
    const rapidez = actual.repeticion ? 1 : pendientes > 6 ? 4 : pendientes > 2 ? 2 : 1;

    const empezarPaso = (paso: Paso, anterior: Paso | undefined) => {
      if (paso.tipo === 'nodo') {
        setNodoActivo(paso.nodo);
        const severidad = SEVERITY_COLOR[fila.severidad ?? ''] ?? '#e2e8f0';
        ondear(paso.nodo, paso.nodo === 'persistencia' ? severidad : P[paso.nodo].color);
        // Desde inferencia en adelante, lo que razonó. Se vuelve a pedir en cada paso porque la
        // justificación puede llegar de la API cuando el recorrido ya pasó por inferencia.
        if (['inferencia', 'validacion', 'persistencia'].includes(paso.nodo)) {
          setPensamiento(textoDelAgente());
        }
        if (paso.nodo === 'persistencia') setResultado(fila);
      } else {
        setNodoActivo(null);
        setRecorridas((r) => new Set(r).add(paso.arista));
        // Al salir de validación se ve el veredicto: una vuelta a inferencia es un reproche.
        if (anterior?.tipo === 'nodo' && anterior.nodo === 'validacion') {
          ondear('validacion', paso.arista === 'validacion>inferencia' ? '#ef4444' : '#00b894');
        }
      }
    };

    const ocultarCometa = () => {
      cabeza.current?.setAttribute('opacity', '0');
      estela.current?.setAttribute('stroke-dasharray', '0 1');
      estelaBrillo.current?.setAttribute('stroke-dasharray', '0 1');
    };

    let i = -1;
    let inicio = 0;
    let marco = 0;
    const cuadro = (ts: number) => {
      if (i === -1 || ts - inicio >= pasos[i].ms / rapidez) {
        i += 1;
        inicio = ts;
        if (i >= pasos.length) {
          setNodoActivo(null);
          ocultarCometa();
          siguiente();
          return;
        }
        empezarPaso(pasos[i], pasos[i - 1]);
      }
      const paso = pasos[i];
      const trazo = paso.tipo === 'arista' ? trazos.current[paso.arista] : null;
      if (trazo) {
        const largo = trazo.getTotalLength();
        const d = Math.min((ts - inicio) / (paso.ms / rapidez), 1) * largo;
        const punto = trazo.getPointAtLength(d);
        cabeza.current?.setAttribute('transform', `translate(${punto.x} ${punto.y})`);
        cabeza.current?.setAttribute('opacity', '1');
        // La estela es el mismo trazo con un solo tramo visible, que termina donde va la cabeza.
        for (const capa of [estela.current, estelaBrillo.current]) {
          capa?.setAttribute('d', trazo.getAttribute('d') ?? '');
          capa?.setAttribute('stroke-dasharray', `${ESTELA} ${largo + ESTELA}`);
          capa?.setAttribute('stroke-dashoffset', String(ESTELA - d));
        }
      } else {
        ocultarCometa();
      }
      marco = requestAnimationFrame(cuadro);
    };
    marco = requestAnimationFrame(cuadro);
    return () => {
      cancelAnimationFrame(marco);
      ocultarCometa();
    };
  }, [actual, siguiente, ondear]);

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

  // Qué parte de la ventana pasó por cada nodo y por cada atajo.
  const total = Math.max(recientes.length, 1);
  const pasaron = (nodo: NodoDelGrafo) => recientes.filter((d) => d.camino.includes(nodo)).length;
  const porArista = (arista: string) =>
    recientes.filter((d) => aristasDe(d.camino).includes(arista)).length;

  const ultima = recientes[0]?.decidida ?? resumen.actividad.ultima;
  const hace = ultima ? Math.max(0, (ahora - new Date(ultima).getTime()) / 1000) : null;
  const activo = hace !== null && hace < MINUTOS_ACTIVO * 60;
  const enPantalla = actual ?? mostrada;
  const enCurso = enPantalla?.fila;
  const partes = pensamiento.split(/(\s+)/);
  // El modelo interviene solo en las decisiones razonadas, y solo mientras el recorrido está en
  // inferencia. Todo el aparato iridiscente cuelga de esto.
  const pensando = nodoActivo === 'inferencia' && !!enCurso?.camino.includes('inferencia');

  const rotulos = [
    { x: 500, y: 21, texto: e.paths.memory, arista: 'memoria>persistencia', color: '#00b894' },
    { x: 665, y: 87, texto: e.paths.retry, arista: 'validacion>inferencia', color: '#d4860a' },
    { x: 542, y: 291, texto: e.paths.noContext, arista: 'contexto>persistencia', color: '#94a3b8' },
  ];
  const destellos = [
    [-44, -30, 7, 0],
    [46, -26, 5.5, 0.4],
    [40, 34, 6.5, 0.8],
    [-40, 36, 5, 1.1],
    [2, -56, 4.5, 0.6],
  ];
  const metricas: [string, string][] = [
    [n(resumen.actividad.ultima_hora), e.lastHour],
    [n(resumen.actividad.copiadas_ultima_hora), e.byMemory],
  ];
  if (resumen.conclusion.mediana_s !== null) {
    metricas.push([duracion(resumen.conclusion.mediana_s), e.toConclusion]);
  }

  return (
    <section
      className="relative overflow-hidden rounded-2xl ring-1 ring-white/10"
      style={{ background: '#090d13' }}
    >
      {/* Aurora de fondo, que se enciende cuando el modelo razona */}
      <div aria-hidden className="absolute inset-0 pointer-events-none">
        <div
          className="motor-aurora absolute -top-40 -left-20 w-[520px] h-[420px] rounded-full"
          style={{
            background: 'radial-gradient(circle, rgba(255,107,53,0.22), transparent 65%)',
            filter: 'blur(40px)',
          }}
        />
        <div
          className="motor-aurora absolute -top-32 right-0 w-[560px] h-[440px] rounded-full transition-opacity duration-700"
          style={{
            background:
              'radial-gradient(circle, rgba(167,139,250,0.24), rgba(56,189,248,0.10) 45%, transparent 70%)',
            filter: 'blur(50px)',
            opacity: pensando ? 1 : 0.3,
            animationDelay: '-6s',
          }}
        />
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: 'radial-gradient(rgba(255,255,255,0.07) 1px, transparent 1px)',
            backgroundSize: '22px 22px',
            maskImage: 'radial-gradient(ellipse at 50% 45%, black 30%, transparent 75%)',
            WebkitMaskImage: 'radial-gradient(ellipse at 50% 45%, black 30%, transparent 75%)',
          }}
        />
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#ff6b35]/60 to-transparent" />
      </div>

      <div className="relative p-4 sm:p-5 flex flex-col gap-3">
        {/* Estado del agente */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 rounded-2xl sm:rounded-full bg-white/[0.04] ring-1 ring-white/10 backdrop-blur px-3.5 py-1.5">
            <span className="relative flex w-2.5 h-2.5">
              {activo && (
                <span className="absolute inline-flex h-full w-full rounded-full bg-[#ff6b35] opacity-60 animate-ping" />
              )}
              <span
                className="relative inline-flex w-2.5 h-2.5 rounded-full"
                style={{ background: activo ? '#ff6b35' : '#94a3b8' }}
              />
            </span>
            <span className="font-mono-display text-[12px] text-white whitespace-nowrap">
              {activo ? e.active : e.idle}
            </span>
            {hace !== null && (
              <span className="font-data text-[10px] text-white/45 whitespace-nowrap">
                {e.lastAgo(duracion(hace))}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-white/50">
            {metricas.map(([valor, texto]) => (
              <span
                key={texto}
                className="rounded-full bg-white/[0.03] ring-1 ring-white/[0.07] px-3 py-1"
              >
                <span className="font-data text-white/90">{valor}</span> {texto}
              </span>
            ))}
            <button
              onClick={repetir}
              disabled={!recientes.length}
              className="group flex items-center gap-1.5 rounded-full px-3 py-1 ring-1 ring-[#ff6b35]/40 bg-[#ff6b35]/10 text-[#ffb38f] hover:bg-[#ff6b35]/20 transition disabled:opacity-30"
            >
              <RotateCcw className="w-3 h-3 transition-transform duration-500 group-hover:-rotate-180" />
              {e.replay}
            </button>
          </div>
        </div>

        {/* El grafo. En un teléfono conserva un ancho mínimo y se desliza de costado: achicado al
            ancho de la pantalla, los nombres de los nodos quedarían ilegibles. */}
        <div className="overflow-x-auto sin-barra -mx-4 px-4 sm:mx-0 sm:px-0">
          <div
            className="relative w-full min-w-[640px]"
            style={{ aspectRatio: `${ANCHO} / ${ALTO}` }}
          >
            <svg viewBox={`0 0 ${ANCHO} ${ALTO}`} className="absolute inset-0 w-full h-full">
              <defs>
                <linearGradient id="motor-ia" x1="0" y1="0" x2="1" y2="1">
                  {IRIDISCENTE.map((c, i) => (
                    <stop key={c} offset={i / (IRIDISCENTE.length - 1)} stopColor={c} />
                  ))}
                </linearGradient>
                <linearGradient id="motor-vidrio" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor="#1c2635" />
                  <stop offset="1" stopColor="#0b1018" />
                </linearGradient>
                <linearGradient id="motor-energia" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0" stopColor="#ff6b35" stopOpacity="0.35" />
                  <stop offset="0.5" stopColor="#ff8a5c" />
                  <stop offset="1" stopColor="#ffd2bd" />
                </linearGradient>
                {NODOS.map((nodo) => (
                  <radialGradient key={nodo.id} id={`motor-halo-${nodo.id}`}>
                    <stop offset="0" stopColor={nodo.color} stopOpacity="0.45" />
                    <stop offset="1" stopColor={nodo.color} stopOpacity="0" />
                  </radialGradient>
                ))}
                <radialGradient id="motor-cabeza">
                  <stop offset="0" stopColor="#ffffff" />
                  <stop offset="0.35" stopColor="#ffd2bd" />
                  <stop offset="1" stopColor="#ff6b35" stopOpacity="0" />
                </radialGradient>
                <filter id="motor-brillo" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur stdDeviation="4" result="difuso" />
                  <feMerge>
                    <feMergeNode in="difuso" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
                <filter id="motor-difuso" x="-100%" y="-100%" width="300%" height="300%">
                  <feGaussianBlur stdDeviation="7" />
                </filter>
              </defs>

              {/* Aristas: la base, y el flujo que corre por ellas mientras el agente trabaja */}
              {Object.entries(ARISTAS).map(([clave, d]) => {
                const encendida = recorridas.has(clave);
                const larga = LARGAS.has(clave);
                return (
                  <g key={clave}>
                    <path
                      id={idDe(clave)}
                      ref={(el) => {
                        trazos.current[clave] = el;
                      }}
                      d={d}
                      fill="none"
                      stroke="rgba(255,255,255,0.10)"
                      strokeWidth={larga ? 1.2 : 1.6}
                      strokeDasharray={larga ? '3 7' : undefined}
                    />
                    <path
                      d={d}
                      fill="none"
                      className="motor-flujo"
                      stroke={encendida ? 'url(#motor-energia)' : 'rgba(148,163,184,0.35)'}
                      strokeWidth={encendida ? 2.4 : 1.2}
                      strokeDasharray="2 12"
                      strokeLinecap="round"
                      filter={encendida ? 'url(#motor-brillo)' : undefined}
                      opacity={encendida ? 1 : activo ? 0.6 : 0}
                      style={{ transition: 'opacity 0.6s, stroke-width 0.4s' }}
                    />
                  </g>
                );
              })}

              {/* Partículas que viajan por las aristas mientras el agente está activo, más densas
                donde más decisiones pasan */}
              {activo &&
                !quieto &&
                Object.keys(ARISTAS).map((clave) => {
                  const cuantas = Math.round((porArista(clave) / total) * 3);
                  const dur = LARGAS.has(clave) ? 7 : 3.2;
                  return Array.from({ length: cuantas }, (_, k) => (
                    <circle
                      key={`${clave}-${k}`}
                      r={1.8}
                      fill={clave === 'memoria>persistencia' ? '#00b894' : '#cbd5e1'}
                      opacity={0.55}
                    >
                      <animateMotion
                        dur={`${dur}s`}
                        begin={`${(k * dur) / cuantas}s`}
                        repeatCount="indefinite"
                      >
                        <mpath href={`#${idDe(clave)}`} />
                      </animateMotion>
                    </circle>
                  ));
                })}

              {/* El contexto que entra al modelo mientras razona */}
              {SINAPSIS.map((d, k) => (
                <g key={d} opacity={pensando ? 1 : 0} style={{ transition: 'opacity 0.5s' }}>
                  <path
                    id={`motor-sinapsis-${k}`}
                    d={d}
                    fill="none"
                    stroke="url(#motor-ia)"
                    strokeWidth={1.6}
                    strokeDasharray="3 9"
                    className="motor-flujo"
                    filter="url(#motor-brillo)"
                  />
                  {pensando &&
                    !quieto &&
                    [0, 1, 2].map((j) => (
                      <circle key={j} r={2.4} fill={IRIDISCENTE[(j + k * 2) % IRIDISCENTE.length]}>
                        <animateMotion dur="1.1s" begin={`${j * 0.36}s`} repeatCount="indefinite">
                          <mpath href={`#motor-sinapsis-${k}`} />
                        </animateMotion>
                      </circle>
                    ))}
                </g>
              ))}

              {/* Rótulos de los tres caminos largos, apoyados sobre la línea */}
              {rotulos.map((r) => {
                const etiqueta = `${r.texto} ${n(porArista(r.arista))}/${n(recientes.length)}`;
                const ancho = etiqueta.length * 6.1 + 24;
                const encendida = recorridas.has(r.arista);
                return (
                  <g key={r.arista}>
                    <rect
                      x={r.x - ancho / 2}
                      y={r.y - 10}
                      width={ancho}
                      height={20}
                      rx={10}
                      fill="#0b1018"
                      stroke={encendida ? '#ff6b35' : r.color}
                      strokeOpacity={encendida ? 0.9 : 0.35}
                      style={{ transition: 'stroke 0.4s' }}
                    />
                    <circle cx={r.x - ancho / 2 + 11} cy={r.y} r={2.5} fill={r.color} />
                    <text
                      x={r.x + 5}
                      y={r.y + 3.6}
                      textAnchor="middle"
                      fontSize={10.5}
                      fill="rgba(255,255,255,0.62)"
                    >
                      {etiqueta}
                    </text>
                  </g>
                );
              })}

              {/* Los nodos */}
              {NODOS.map((nodo) => {
                const activoAca = nodoActivo === nodo.id;
                const esIA = nodo.id === 'inferencia';
                const circunferencia = 2 * Math.PI * 45;
                return (
                  <g key={nodo.id} className="motor-nodo" data-activo={activoAca ? 'si' : 'no'}>
                    <circle
                      cx={nodo.x}
                      cy={nodo.y}
                      r={62}
                      fill={`url(#motor-halo-${nodo.id})`}
                      opacity={activoAca ? 1 : 0.28}
                      style={{ transition: 'opacity 0.5s' }}
                    />
                    {/* El aura del modelo: tenue siempre, encendida cuando razona */}
                    {esIA && (
                      <circle
                        cx={nodo.x}
                        cy={nodo.y}
                        r={49}
                        fill="none"
                        stroke="url(#motor-ia)"
                        strokeWidth={pensando ? 5 : 2}
                        opacity={pensando ? 0.95 : 0.22}
                        filter="url(#motor-difuso)"
                        className="motor-giro-rapido"
                        style={{ transition: 'opacity 0.5s, stroke-width 0.5s' }}
                      />
                    )}
                    {/* Anillo de uso: qué parte de las últimas decisiones pasó por acá */}
                    <circle
                      cx={nodo.x}
                      cy={nodo.y}
                      r={45}
                      fill="none"
                      stroke="rgba(255,255,255,0.06)"
                      strokeWidth={2}
                    />
                    <circle
                      cx={nodo.x}
                      cy={nodo.y}
                      r={45}
                      fill="none"
                      stroke={esIA ? 'url(#motor-ia)' : nodo.color}
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeDasharray={`${(pasaron(nodo.id) / total) * circunferencia} ${circunferencia}`}
                      transform={`rotate(-90 ${nodo.x} ${nodo.y})`}
                      opacity={0.75}
                      style={{ transition: 'stroke-dasharray 0.9s ease' }}
                    >
                      <title>{e.ring(pasaron(nodo.id), recientes.length)}</title>
                    </circle>
                    {activoAca && (
                      <circle
                        cx={nodo.x}
                        cy={nodo.y}
                        r={39}
                        fill="none"
                        stroke={esIA && pensando ? 'url(#motor-ia)' : nodo.color}
                        strokeWidth={1.2}
                        strokeDasharray="2 6"
                        className="motor-giro"
                      />
                    )}
                    <polygon
                      points={hexagono(nodo.x, nodo.y, R)}
                      fill="url(#motor-vidrio)"
                      stroke={esIA && pensando ? 'url(#motor-ia)' : nodo.color}
                      strokeOpacity={activoAca ? 1 : 0.55}
                      strokeWidth={activoAca ? 2.4 : 1.4}
                      style={{ transition: 'stroke-opacity 0.4s, stroke-width 0.4s' }}
                    />
                    <polygon
                      points={hexagono(nodo.x, nodo.y, R * 0.72)}
                      fill="none"
                      stroke={nodo.color}
                      strokeOpacity={0.14}
                    />
                  </g>
                );
              })}

              {/* Destellos alrededor del modelo mientras razona */}
              {pensando &&
                !quieto &&
                destellos.map(([dx, dy, r, retraso]) => (
                  <path
                    key={`${dx}-${dy}`}
                    d={estrella(P.inferencia.x + dx, P.inferencia.y + dy, r)}
                    fill="url(#motor-ia)"
                    className="motor-destello"
                    style={{ animationDelay: `${retraso}s` }}
                  />
                ))}

              {/* Ondas: cada llegada a un nodo, y el veredicto de la validación */}
              {!quieto &&
                ondas.map((o) => (
                  <polygon
                    key={o.clave}
                    points={hexagono(P[o.nodo].x, P[o.nodo].y, R)}
                    fill="none"
                    stroke={o.color}
                    strokeWidth={2}
                    className="motor-onda"
                    onAnimationEnd={() =>
                      setOndas((todas) => todas.filter((x) => x.clave !== o.clave))
                    }
                  />
                ))}

              {/* El cometa: estela y cabeza */}
              <path
                ref={estela}
                fill="none"
                stroke="#ff6b35"
                strokeWidth={7}
                strokeLinecap="round"
                opacity={0.45}
                filter="url(#motor-difuso)"
                strokeDasharray="0 1"
              />
              <path
                ref={estelaBrillo}
                fill="none"
                stroke="url(#motor-energia)"
                strokeWidth={2.6}
                strokeLinecap="round"
                strokeDasharray="0 1"
              />
              <g ref={cabeza} opacity={0}>
                <circle r={14} fill="url(#motor-cabeza)" opacity={0.8} />
                <circle r={3.6} fill="#fff" />
              </g>
            </svg>

            {/* Íconos y nombres de cada nodo, encima del dibujo */}
            {NODOS.map((nodo) => {
              const Icono = nodo.icono;
              const activoAca = nodoActivo === nodo.id;
              const iridiscente = nodo.id === 'inferencia' && pensando;
              return (
                <div key={nodo.id}>
                  <Icono
                    className="absolute w-5 h-5 -translate-x-1/2 -translate-y-1/2 transition-all duration-300"
                    style={{
                      left: `${(nodo.x / ANCHO) * 100}%`,
                      top: `${(nodo.y / ALTO) * 100}%`,
                      color: activoAca ? '#ffffff' : nodo.color,
                      filter: activoAca ? `drop-shadow(0 0 6px ${nodo.color})` : undefined,
                    }}
                  />
                  <div
                    className="absolute -translate-x-1/2 flex flex-col items-center"
                    style={{
                      left: `${(nodo.x / ANCHO) * 100}%`,
                      top: `${((nodo.y + R + 17) / ALTO) * 100}%`,
                    }}
                  >
                    <span
                      className={`font-mono-display text-[11px] tracking-wide transition-colors duration-300 ${
                        iridiscente ? 'motor-iridiscente' : ''
                      }`}
                      style={{
                        color: iridiscente
                          ? undefined
                          : activoAca
                            ? '#ffffff'
                            : 'rgba(255,255,255,0.62)',
                      }}
                    >
                      {e.nodes[nodo.id].name}
                    </span>
                    {iridiscente && (
                      <span className="flex items-end gap-[2px] h-2.5 mt-1" aria-hidden>
                        {IRIDISCENTE.map((color, b) => (
                          <span
                            key={color}
                            className="motor-barra w-[2px] h-full rounded-full"
                            style={{ background: color, animationDelay: `${b * 0.12}s` }}
                          />
                        ))}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Lo que acaba de guardar la persistencia */}
            {resultado && (
              <div
                key={resultado.doc_id}
                className="motor-aparece absolute -translate-x-1/2 rounded-lg px-2.5 py-1 text-[10px] font-medium whitespace-nowrap backdrop-blur"
                style={{
                  left: `${(P.persistencia.x / ANCHO) * 100 - 1}%`,
                  top: `${((P.persistencia.y + R + 44) / ALTO) * 100}%`,
                  color: SEVERITY_COLOR[resultado.severidad ?? ''] ?? 'rgba(255,255,255,0.7)',
                  background: 'rgba(9,13,19,0.85)',
                  boxShadow: `inset 0 0 0 1px ${SEVERITY_COLOR[resultado.severidad ?? ''] ?? '#475569'}, 0 0 18px ${
                    SEVERITY_COLOR[resultado.severidad ?? ''] ?? '#475569'
                  }55`,
                }}
              >
                {resultado.severidad
                  ? t.severities[resultado.severidad as keyof typeof t.severities]
                  : t.triage.notConcluded}
                {resultado.tactica_mitre ? `, ${tacticName(resultado.tactica_mitre)}` : ''}
              </div>
            )}
          </div>
        </div>

        {/* Qué está haciendo el agente, y lo que va llegando */}
        <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-3">
          <div
            className="motor-borde rounded-xl flex flex-col"
            data-pensando={pensando && !quieto ? 'si' : 'no'}
          >
            <div className="motor-borde-interior flex-1 rounded-xl bg-[#0b1018] ring-1 ring-white/[0.07] p-3.5 min-h-[138px]">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span className="flex items-center gap-2 min-w-0">
                  <span
                    className={`text-[9px] uppercase tracking-[0.14em] shrink-0 ${
                      pensando ? 'motor-iridiscente' : 'text-[#ff8a5c]'
                    }`}
                  >
                    {e.thinking}
                  </span>
                  {nodoActivo && (
                    <span
                      key={nodoActivo}
                      className="motor-aparece truncate rounded-full px-2 py-0.5 text-[9px] font-mono-display"
                      style={{
                        color: P[nodoActivo].color,
                        boxShadow: `inset 0 0 0 1px ${P[nodoActivo].color}55`,
                      }}
                    >
                      {e.nodes[nodoActivo].name}: {e.nodes[nodoActivo].what}
                    </span>
                  )}
                </span>
                {enPantalla?.repeticion && (
                  <span className="text-[9px] rounded-full px-2 py-0.5 ring-1 ring-white/15 text-white/45 shrink-0">
                    {e.replaying}
                  </span>
                )}
              </div>
              {enCurso ? (
                <>
                  <div className="font-data text-[11px] text-white/55 mt-2.5 truncate">
                    {enCurso.resumen}
                  </div>
                  <p className="text-[12.5px] text-white/85 mt-2 leading-relaxed">
                    {partes.slice(0, palabras).map((parte, k) => (
                      <span key={k} className="motor-token">
                        {parte}
                      </span>
                    ))}
                    <span
                      className="terminal-cursor inline-block w-1.5 h-3.5 ml-0.5 align-middle rounded-sm"
                      style={{
                        background: pensando ? 'linear-gradient(#f472b6, #38bdf8)' : '#ff6b35',
                      }}
                    />
                  </p>
                  {enCurso.modelo && (
                    <div className="flex flex-wrap gap-1.5 mt-2.5">
                      {[
                        enCurso.modelo,
                        enCurso.segundos != null ? `${dec(enCurso.segundos, 1)} s` : null,
                        enCurso.costo_usd != null ? `USD ${dec(enCurso.costo_usd, 5)}` : null,
                        enCurso.rechazos ? e.retries(enCurso.rechazos) : null,
                      ]
                        .filter((dato): dato is string => Boolean(dato))
                        .map((dato) => (
                          <span
                            key={dato}
                            className="font-data text-[9.5px] rounded-md px-1.5 py-0.5 text-white/60 bg-white/[0.04] ring-1 ring-white/[0.08]"
                          >
                            {dato}
                          </span>
                        ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="text-[12px] text-white/40 mt-2.5">{error ?? e.waiting}</div>
              )}
            </div>
          </div>

          <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/[0.07] p-3.5">
            <div className="rotulo">{e.feed}</div>
            <ul className="mt-2 flex flex-col gap-0.5">
              {recientes.slice(0, 7).map((d) => {
                const esta = enCurso?.doc_id === d.doc_id;
                const tipo = d.copiada
                  ? e.paths.memory
                  : d.motivo_de_corte === 'sin_contexto'
                    ? e.paths.noContext
                    : d.rechazos
                      ? e.retries(d.rechazos)
                      : e.paths.full;
                return (
                  <li key={d.doc_id} className="motor-entrada">
                    <button
                      onClick={() => onElegir(d.doc_id)}
                      className={`relative w-full grid grid-cols-[56px_minmax(0,1fr)_auto] sm:grid-cols-[62px_110px_minmax(0,1fr)_auto] gap-2 items-center rounded-md px-2 py-1 text-left transition ${
                        esta ? 'bg-white/[0.05]' : 'hover:bg-white/[0.03]'
                      }`}
                    >
                      {esta && (
                        <span
                          className="absolute left-0 top-1 bottom-1 w-[2px] rounded-full"
                          style={{
                            background: d.copiada
                              ? '#00b894'
                              : 'linear-gradient(#ff6b35, #f472b6, #a78bfa)',
                          }}
                        />
                      )}
                      <span className="font-data text-[10px] text-white/40">
                        {hora(d.decidida)}
                      </span>
                      <span
                        className={`text-[10px] truncate ${d.copiada ? '' : 'motor-iridiscente'}`}
                        style={{ color: d.copiada ? '#00b894' : undefined }}
                      >
                        {tipo}
                      </span>
                      <span className="hidden sm:block font-data text-[10px] text-white/65 truncate">
                        {d.resumen}
                      </span>
                      <span
                        className="text-[10px] font-medium"
                        style={{
                          color: SEVERITY_COLOR[d.severidad ?? ''] ?? 'rgba(255,255,255,0.4)',
                        }}
                      >
                        {d.severidad
                          ? t.severities[d.severidad as keyof typeof t.severities]
                          : t.triage.notConcluded}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
