import { useEffect, useMemo, useRef, useState } from 'react';
// Con alias porque `PointerEvent` sin él tapa al del DOM, y en un archivo que maneja punteros esa
// ambigüedad se paga cara.
import type { PointerEvent as EventoPuntero } from 'react';
import type { CountryOrigin } from '../lib/api';
import { WORLD } from '../lib/world';
import { nombreDePais } from '../lib/format';

/**
 * Globo que rota, con las fronteras de los países y un marcador por país de origen.
 *
 * Está dibujado como una proyección ortográfica en SVG y no con una biblioteca 3D. Las fronteras
 * salen de Natural Earth, decodificadas y simplificadas de antemano por scripts/build_world_map.py:
 * 28 KB de pares de coordenadas pelados, contra el megabyte que una biblioteca de globos le sumaría
 * al panel.
 *
 * Las coordenadas de cada marcador son el centroide de las direcciones efectivamente observadas en
 * ese país, calculado por Elasticsearch sobre los eventos capturados. No son el centro geográfico
 * del país: si todos los ataques de un país vinieron de una ciudad, el marcador queda en esa
 * ciudad.
 */

const R = 78; // radio de la esfera, en unidades del viewBox
const CX = 100;
const CY = 100;
const RAD = Math.PI / 180;

// Inclinación inicial del eje. Con el globo derecho, el hemisferio norte (de donde viene casi todo
// el tráfico) queda comprimido contra el borde superior. Arrastrando en vertical se cambia.
const TILT = 18;

// Tope de la inclinación manual. Más allá del polo la proyección sigue siendo válida pero el mundo
// aparece invertido, que se lee como un error de dibujo y no como una vista elegida.
const TILT_MAX = 80;

// Un arrastre del ancho del globo da media vuelta. Se mide contra el ancho real del elemento y no
// en píxeles fijos, para que el gesto se sienta igual en el panel y en un teléfono.
const GRADOS_POR_ANCHO = 180;

// Movimiento por debajo del cual el gesto sigue siendo un clic. Sin esto, el temblor de la mano al
// soltar sobre un marcador alcanzaba para que el clic no llegara a seleccionar el país.
const UMBRAL_CLIC = 4;

interface Punto {
  x: number;
  y: number;
  visible: boolean;
  /** Profundidad: 1 al frente, 0 en el borde. Se usa para desvanecer lo que se va de lado. */
  z: number;
}

/** Proyección ortográfica de una lat/lon sobre la esfera, para una rotación e inclinación dadas. */
function proyectar(lat: number, lon: number, rotLon: number, tilt: number): Punto {
  const l = (lon + rotLon) * RAD;
  const f = lat * RAD;
  const f0 = tilt * RAD;

  const cosc = Math.sin(f0) * Math.sin(f) + Math.cos(f0) * Math.cos(f) * Math.cos(l);
  return {
    x: CX + R * Math.cos(f) * Math.sin(l),
    y: CY - R * (Math.cos(f0) * Math.sin(f) - Math.sin(f0) * Math.cos(f) * Math.cos(l)),
    visible: cosc > 0,
    z: Math.max(0, cosc),
  };
}

/**
 * Meridianos y paralelos como cadenas de path, cortados donde pasan por detrás de la esfera.
 *
 * Sin ese corte, una línea que se va del lado visible se dibujaría derecho cruzando el disco hasta
 * donde reaparece, y eso se lee como una grieta y no como una curva.
 */
function graticula(rotLon: number, tilt: number): string[] {
  const paths: string[] = [];

  const traza = (puntos: Punto[]) => {
    let d = '';
    let dibujando = false;
    for (const p of puntos) {
      if (!p.visible) {
        dibujando = false;
        continue;
      }
      d += `${dibujando ? 'L' : 'M'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
      dibujando = true;
    }
    if (d) paths.push(d);
  };

  for (let lon = -180; lon < 180; lon += 30) {
    const puntos: Punto[] = [];
    for (let lat = -90; lat <= 90; lat += 5) puntos.push(proyectar(lat, lon, rotLon, tilt));
    traza(puntos);
  }
  for (let lat = -60; lat <= 60; lat += 30) {
    const puntos: Punto[] = [];
    for (let lon = -180; lon <= 180; lon += 5) puntos.push(proyectar(lat, lon, rotLon, tilt));
    traza(puntos);
  }
  return paths;
}

// Entre cuadro y cuadro lo único que cambia es la rotación, así que el seno y el coseno propios de
// cada punto se sacan una sola vez. Con las identidades de suma de ángulos, proyectar dos mil
// puntos por cuadro pasa a ser multiplicaciones y no ocho mil llamadas trigonométricas.
interface PuntoFijo {
  sinF: number;
  cosF: number;
  sinL: number;
  cosL: number;
}

function precomputar(anillos: [number, number][][]): PuntoFijo[][] {
  return anillos.map((anillo) =>
    anillo.map(([lon, lat]) => ({
      sinF: Math.sin(lat * RAD),
      cosF: Math.cos(lat * RAD),
      sinL: Math.sin(lon * RAD),
      cosL: Math.cos(lon * RAD),
    })),
  );
}

/**
 * Los anillos de las fronteras como cadenas de path, cortados donde pasan por detrás de la esfera.
 *
 * Es el mismo corte que en la graticula y por el mismo motivo: un anillo que se va del lado visible
 * se dibujaría derecho cruzando el disco hasta donde vuelve.
 */
function contornos(anillos: PuntoFijo[][], rotLon: number, tilt: number): string {
  const sinR = Math.sin(rotLon * RAD);
  const cosR = Math.cos(rotLon * RAD);
  const sinF0 = Math.sin(tilt * RAD);
  const cosF0 = Math.cos(tilt * RAD);

  let d = '';
  for (const anillo of anillos) {
    let dibujando = false;
    for (const p of anillo) {
      // sin(lon + rot) y cos(lon + rot) por identidad de suma de ángulos
      const sinL = p.sinL * cosR + p.cosL * sinR;
      const cosL = p.cosL * cosR - p.sinL * sinR;

      if (sinF0 * p.sinF + cosF0 * p.cosF * cosL <= 0) {
        dibujando = false;
        continue;
      }
      const x = CX + R * p.cosF * sinL;
      const y = CY - R * (cosF0 * p.sinF - sinF0 * p.cosF * cosL);
      d += `${dibujando ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`;
      dibujando = true;
    }
  }
  return d;
}

/**
 * Si el globo tiene que saltearse la animación e ir directo a su destino.
 *
 * Pasa en dos casos, los dos reales: el lector pidió movimiento reducido, o la pestaña está en
 * segundo plano, donde los navegadores directamente no ejecutan requestAnimationFrame.
 */
function sinAnimacion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches || document.hidden;
}

/** La distancia angular más corta: de 170 grados a menos 170 hay 20 grados, no 340. */
function deltaAngular(desde: number, hasta: number): number {
  return ((((hasta - desde) % 360) + 540) % 360) - 180;
}

/**
 * Qué gobierna la rotación en este momento.
 *
 * Una sola pregunta (¿hay país elegido?) no alcanza: en cuanto el arrastre puede mover el globo,
 * hace falta distinguir "nadie lo tocó" de "el usuario lo dejó así". Si no, soltar el mouse con un
 * país elegido devolvería el globo a su posición y el gesto parecería no haber pasado.
 */
type Modo = 'auto' | 'destino' | 'libre';

interface Arrastre {
  x: number;
  y: number;
  rot: number;
  tilt: number;
  /** Ancho del elemento al empezar: el gesto se mide en fracciones de él, no en píxeles. */
  ancho: number;
}

interface Props {
  countries: CountryOrigin[];
  selected: string | null;
  onSelect: (country: string | null) => void;
}

export default function Globe({ countries, selected, onSelect }: Props) {
  const [rotLon, setRotLon] = useState(0);
  const [tilt, setTilt] = useState(TILT);
  const rotRef = useRef(0);
  const tiltRef = useRef(TILT);
  const destinoRef = useRef<number | null>(null);
  const rafRef = useRef<number | undefined>(undefined);
  const modoRef = useRef<Modo>('auto');
  const arrastreRef = useRef<Arrastre | null>(null);
  // Sobrevive al pointerup a propósito: el clic del navegador llega después, y es ahí donde hay que
  // saber si el gesto fue un clic o el final de un arrastre.
  const movidoRef = useRef(false);
  const [arrastrando, setArrastrando] = useState(false);

  // Se calcula una sola vez: el contorno del mundo no cambia entre fotogramas ni entre datos.
  const mundo = useMemo(() => precomputar(WORLD), []);
  const conCoords = countries.filter((c) => c.lat != null && c.lon != null);
  const max = Math.max(...conCoords.map((c) => c.count), 1);

  // Al elegir un país, el destino de la rotación es el que lo deja de frente.
  useEffect(() => {
    if (!selected) {
      destinoRef.current = null;
      modoRef.current = 'auto';
      return;
    }
    const pais = conCoords.find((c) => c.country === selected);
    if (pais?.lon == null) return;

    const destino = -pais.lon;
    destinoRef.current = destino;
    // Elegir un país recupera el control aunque el usuario hubiera movido el globo a mano: es una
    // orden explícita ("mostrame este") y tiene que ganarle al encuadre anterior.
    modoRef.current = 'destino';

    // Si la animación no puede correr, se salta directo al destino en lugar de no moverse. Sin
    // esto, con "reducir movimiento" o con la pestaña de fondo, elegir un país dejaría el marcador
    // donde está y la selección parecería no hacer nada. Centrar el país es la función y el giro es
    // la decoración: entre las dos se conserva la función.
    if (sinAnimacion()) {
      rotRef.current = destino;
      setRotLon(destino);
    }
  }, [selected, countries]);

  useEffect(() => {
    const paso = () => {
      // El modo captura congela el resto del panel desde CSS, que no alcanza para una animación
      // por fotograma: hay que detenerla acá o el globo seguiría girando durante la captura.
      const congelado = document.documentElement.dataset.capture === 'on';

      // En modo libre el globo queda donde lo dejó el usuario. El bucle sigue vivo igual, para que
      // volver a 'auto' o a 'destino' no tenga que arrancarlo de nuevo.
      if (!congelado && modoRef.current !== 'libre') {
        const destino = destinoRef.current;
        if (modoRef.current === 'destino' && destino != null) {
          const d = deltaAngular(rotRef.current, destino);
          // Frenado exponencial: rápido al principio y suave al llegar, sin rebote.
          rotRef.current += Math.abs(d) < 0.15 ? d : d * 0.06;
        } else {
          rotRef.current = (rotRef.current + 0.12) % 360;
        }
        setRotLon(rotRef.current);
      }
      rafRef.current = requestAnimationFrame(paso);
    };

    const arrancar = () => {
      if (rafRef.current !== undefined || sinAnimacion()) return;
      rafRef.current = requestAnimationFrame(paso);
    };
    const parar = () => {
      if (rafRef.current === undefined) return;
      cancelAnimationFrame(rafRef.current);
      rafRef.current = undefined;
    };

    // Volver de segundo plano tiene que revivir el giro. Si la condición se mirara solo al montar,
    // abrir el panel en una pestaña de fondo dejaría el bucle sin arrancar y traerla al frente
    // después no lo reviviría: el globo quedaría muerto para toda la visita.
    const alCambiarVisibilidad = () => (document.hidden ? parar() : arrancar());
    document.addEventListener('visibilitychange', alCambiarVisibilidad);
    arrancar();

    return () => {
      document.removeEventListener('visibilitychange', alCambiarVisibilidad);
      parar();
    };
  }, []);

  const alBajar = (e: EventoPuntero<SVGSVGElement>) => {
    const ancho = e.currentTarget.getBoundingClientRect().width || 1;
    arrastreRef.current = {
      x: e.clientX,
      y: e.clientY,
      rot: rotRef.current,
      tilt: tiltRef.current,
      ancho,
    };
    movidoRef.current = false;
    modoRef.current = 'libre';
    setArrastrando(true);
    // Con captura, el gesto sobrevive a que el puntero se salga del círculo: sin ella, arrastrar
    // rápido suelta el globo a mitad de camino.
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const alMover = (e: EventoPuntero<SVGSVGElement>) => {
    const a = arrastreRef.current;
    if (!a) return;
    const dx = e.clientX - a.x;
    const dy = e.clientY - a.y;
    if (!movidoRef.current && Math.hypot(dx, dy) > UMBRAL_CLIC) movidoRef.current = true;

    rotRef.current = a.rot + (dx / a.ancho) * GRADOS_POR_ANCHO;
    // Hacia abajo se mira más al norte: el hemisferio que se arrastra es el que se acerca.
    const t = a.tilt + (dy / a.ancho) * GRADOS_POR_ANCHO;
    tiltRef.current = Math.max(-TILT_MAX, Math.min(TILT_MAX, t));

    setRotLon(rotRef.current);
    setTilt(tiltRef.current);
  };

  const alSoltar = (e: EventoPuntero<SVGSVGElement>) => {
    arrastreRef.current = null;
    setArrastrando(false);
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    // Sin país elegido el giro continuo se retoma desde donde quedó, porque es la animación de
    // fondo de la sección. Con uno elegido se respeta el encuadre: para eso el usuario lo movió.
    if (!selected) modoRef.current = 'auto';
  };

  const lineas = graticula(rotLon, tilt);
  const contornosPath = contornos(mundo, rotLon, tilt);

  return (
    <svg
      viewBox="0 0 200 200"
      className="w-full h-full select-none"
      role="img"
      aria-label="Globo terráqueo"
      onPointerDown={alBajar}
      onPointerMove={alMover}
      onPointerUp={alSoltar}
      onPointerCancel={alSoltar}
      /* touchAction none: sin esto, en pantalla táctil el gesto lo toma el desplazamiento de la
         página y el globo no se entera. */
      style={{ touchAction: 'none', cursor: arrastrando ? 'grabbing' : 'grab' }}
    >
      <defs>
        {/* Atmósfera: un halo apenas por fuera del borde, para que la esfera no quede recortada
            contra el fondo como un círculo plano. */}
        <radialGradient id="g-atmosfera">
          <stop offset="70%" stopColor="var(--neural-teal)" stopOpacity="0" />
          <stop offset="94%" stopColor="var(--neural-teal)" stopOpacity="0.16" />
          <stop offset="100%" stopColor="var(--neural-teal)" stopOpacity="0" />
        </radialGradient>
        {/* Sombreado del cuerpo: iluminado desde arriba a la izquierda, para dar volumen. */}
        <radialGradient id="g-cuerpo" cx="36%" cy="30%">
          <stop offset="0%" stopColor="var(--globo-luz)" />
          <stop offset="100%" stopColor="var(--globo-sombra)" />
        </radialGradient>
        <filter id="f-costa">
          <feGaussianBlur stdDeviation="1.4" />
        </filter>
        <filter id="f-brillo">
          <feGaussianBlur stdDeviation="2.2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <circle cx={CX} cy={CY} r={R + 14} fill="url(#g-atmosfera)" />
      <circle cx={CX} cy={CY} r={R} fill="url(#g-cuerpo)" />

      {/* La retícula va debajo y más tenue: da la forma de la esfera, pero lo que se lee son los
          contornos. Dos tramas del mismo peso compiten y ninguna se distingue. */}
      <g stroke="rgb(var(--tinta) / 0.09)" strokeWidth="0.35" fill="none">
        {lineas.map((d, i) => (
          <path key={i} d={d} />
        ))}
      </g>

      {/* Los contornos van en el verde de la paleta, no en blanco: el blanco es el color del texto
          en todo el panel y usarlo acá hacía competir al mapa con lo que hay que leer. Se dibujan
          dos veces, una difusa por debajo, para que las costas tengan el mismo halo que el resto
          de los elementos de la interfaz. */}
      <path
        d={contornosPath}
        fill="none"
        stroke="var(--neural-teal)"
        strokeWidth="1.6"
        strokeLinejoin="round"
        opacity="0.14"
        filter="url(#f-costa)"
      />
      <path
        d={contornosPath}
        fill="none"
        stroke="var(--neural-teal)"
        strokeWidth="0.4"
        strokeLinejoin="round"
        opacity="0.55"
      />

      <circle cx={CX} cy={CY} r={R} fill="none" stroke="rgba(0,184,148,0.28)" strokeWidth="0.6" />

      {conCoords.map((c) => {
        const p = proyectar(c.lat as number, c.lon as number, rotLon, tilt);
        if (!p.visible) return null;

        const esSel = selected === c.country;
        // El radio sale de la raíz del volumen: en escala lineal, el país que lidera aplasta al
        // resto y todos los demás quedan del mismo tamaño.
        const r = 1.6 + Math.sqrt(c.count / max) * 4.2;
        const color = esSel ? 'var(--agent-coral)' : 'var(--honey-amber)';

        return (
          <g
            key={c.country}
            /* Soltar el arrastre encima de un marcador no lo selecciona: el clic del navegador
               llega igual, y sin esta guardia girar el globo terminaba eligiendo un país al
               azar, el que quedara bajo el cursor. */
            onClick={() => {
              if (movidoRef.current) return;
              onSelect(esSel ? null : c.country);
            }}
            style={{ cursor: 'pointer' }}
            opacity={0.35 + p.z * 0.65}
          >
            {esSel && (
              <circle cx={p.x} cy={p.y} r={r + 4} fill="none" stroke={color} strokeWidth="0.7">
                <animate
                  attributeName="r"
                  values={`${r + 2};${r + 9};${r + 2}`}
                  dur="2.4s"
                  repeatCount="indefinite"
                />
                <animate
                  attributeName="opacity"
                  values="0.9;0;0.9"
                  dur="2.4s"
                  repeatCount="indefinite"
                />
              </circle>
            )}
            <circle cx={p.x} cy={p.y} r={r} fill={color} filter="url(#f-brillo)" />
            <title>{nombreDePais(c.iso, c.country)}</title>
          </g>
        );
      })}
    </svg>
  );
}
