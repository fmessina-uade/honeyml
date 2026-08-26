import { useEffect, useMemo, useRef, useState } from 'react';
import type { CountryOrigin } from '../lib/api';
import { WORLD } from '../lib/world';

/**
 * Rotating globe with country borders and a marker per country of origin.
 *
 * Drawn as an SVG orthographic projection rather than with a 3D library. The borders come from
 * Natural Earth, decoded and simplified ahead of time by scripts/build_world_map.py: 28 KB of
 * plain coordinate pairs, against the megabyte a globe library would add to a bundle that ships
 * at 250 KB.
 *
 * The marker coordinates are the centroid of the addresses actually observed in each country,
 * computed by Elasticsearch over the captured events. They are not the country's geographic
 * centre: if every attack from a country came from one city, the marker sits on that city.
 */

const R = 78; // radio de la esfera, en unidades del viewBox
const CX = 100;
const CY = 100;
const RAD = Math.PI / 180;

// Inclinación fija del eje. Con el globo derecho, el hemisferio norte —de donde viene casi todo el
// tráfico— queda comprimido contra el borde superior.
const TILT = 18;

interface Punto {
  x: number;
  y: number;
  visible: boolean;
  /** Profundidad: 1 al frente, 0 en el borde. Se usa para desvanecer lo que se va de lado. */
  z: number;
}

/** Orthographic projection of a lat/lon onto the sphere, for a given rotation. */
function proyectar(lat: number, lon: number, rotLon: number): Punto {
  const l = (lon + rotLon) * RAD;
  const f = lat * RAD;
  const f0 = TILT * RAD;

  const cosc = Math.sin(f0) * Math.sin(f) + Math.cos(f0) * Math.cos(f) * Math.cos(l);
  return {
    x: CX + R * Math.cos(f) * Math.sin(l),
    y: CY - R * (Math.cos(f0) * Math.sin(f) - Math.sin(f0) * Math.cos(f) * Math.cos(l)),
    visible: cosc > 0,
    z: Math.max(0, cosc),
  };
}

/**
 * Meridians and parallels as path strings, broken wherever they cross behind the sphere.
 *
 * Without the break, a line leaving the visible side would be drawn straight across the disc to
 * wherever it reappears, which reads as a crack rather than as a curve.
 */
function graticula(rotLon: number): string[] {
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
    for (let lat = -90; lat <= 90; lat += 5) puntos.push(proyectar(lat, lon, rotLon));
    traza(puntos);
  }
  for (let lat = -60; lat <= 60; lat += 30) {
    const puntos: Punto[] = [];
    for (let lon = -180; lon <= 180; lon += 5) puntos.push(proyectar(lat, lon, rotLon));
    traza(puntos);
  }
  return paths;
}

/**
 * Every border point with its trigonometry precomputed.
 *
 * Only the rotation changes between frames, so the sine and cosine of each point's own latitude
 * and longitude are constant and can be worked out once. With the angle-sum identities, projecting
 * two thousand points per frame becomes multiplications instead of eight thousand trig calls.
 */
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
 * Border rings as path strings, cut wherever they pass behind the sphere.
 *
 * Same cut as the graticule and for the same reason: a ring that leaves the visible side would
 * otherwise be drawn straight across the disc to wherever it comes back.
 */
function contornos(anillos: PuntoFijo[][], rotLon: number): string {
  const sinR = Math.sin(rotLon * RAD);
  const cosR = Math.cos(rotLon * RAD);
  const sinF0 = Math.sin(TILT * RAD);
  const cosF0 = Math.cos(TILT * RAD);

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
 * Whether the globe should skip animating and jump straight to its target.
 *
 * Two cases, both real: the reader asked for reduced motion, or the tab is in the background,
 * where browsers do not run requestAnimationFrame at all.
 */
function sinAnimacion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches || document.hidden;
}

/** Shortest angular distance, so rotating from 170° to −170° goes 20° and not 340°. */
function deltaAngular(desde: number, hasta: number): number {
  return ((((hasta - desde) % 360) + 540) % 360) - 180;
}

interface Props {
  countries: CountryOrigin[];
  selected: string | null;
  onSelect: (country: string | null) => void;
}

export default function Globe({ countries, selected, onSelect }: Props) {
  const [rotLon, setRotLon] = useState(0);
  const rotRef = useRef(0);
  const destinoRef = useRef<number | null>(null);
  const rafRef = useRef<number | undefined>(undefined);

  // Se calcula una sola vez: el contorno del mundo no cambia entre fotogramas ni entre datos.
  const mundo = useMemo(() => precomputar(WORLD), []);
  const conCoords = countries.filter((c) => c.lat != null && c.lon != null);
  const max = Math.max(...conCoords.map((c) => c.count), 1);

  // Al elegir un país, el destino de la rotación es el que lo deja de frente.
  useEffect(() => {
    if (!selected) {
      destinoRef.current = null;
      return;
    }
    const pais = conCoords.find((c) => c.country === selected);
    if (pais?.lon == null) return;

    const destino = -pais.lon;
    destinoRef.current = destino;

    // Si la animación no puede correr, se salta directo al destino en lugar de no moverse.
    //
    // Pasa en dos situaciones reales: con "reducir movimiento" activado, y con la pestaña en
    // segundo plano, donde el navegador no ejecuta requestAnimationFrame. Sin este salto, elegir
    // un país dejaba el marcador donde estaba y la selección parecía no hacer nada — que es
    // exactamente cómo se detectó.
    //
    // Centrar el país es la función; el giro es la decoración. Cuando hay que elegir entre las
    // dos, se conserva la función.
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

      if (!congelado) {
        const destino = destinoRef.current;
        if (destino != null) {
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

    if (!sinAnimacion()) rafRef.current = requestAnimationFrame(paso);
    return () => {
      if (rafRef.current !== undefined) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const lineas = graticula(rotLon);

  return (
    <svg viewBox="0 0 200 200" className="w-full h-full" role="img" aria-label="Globo terráqueo">
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
          <stop offset="0%" stopColor="#1b2836" />
          <stop offset="100%" stopColor="#0c1219" />
        </radialGradient>
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
      <g stroke="rgba(148,163,184,0.10)" strokeWidth="0.35" fill="none">
        {lineas.map((d, i) => (
          <path key={i} d={d} />
        ))}
      </g>

      <path
        d={contornos(mundo, rotLon)}
        fill="none"
        stroke="rgba(148,163,184,0.42)"
        strokeWidth="0.45"
        strokeLinejoin="round"
      />

      <circle cx={CX} cy={CY} r={R} fill="none" stroke="rgba(0,184,148,0.28)" strokeWidth="0.6" />

      {conCoords.map((c) => {
        const p = proyectar(c.lat as number, c.lon as number, rotLon);
        if (!p.visible) return null;

        const esSel = selected === c.country;
        // El radio sale de la raíz del volumen: en escala lineal, el país que lidera aplasta al
        // resto y todos los demás quedan del mismo tamaño.
        const r = 1.6 + Math.sqrt(c.count / max) * 4.2;
        const color = esSel ? 'var(--agent-coral)' : 'var(--honey-amber)';

        return (
          <g
            key={c.country}
            onClick={() => onSelect(esSel ? null : c.country)}
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
            <title>{c.country}</title>
          </g>
        );
      })}
    </svg>
  );
}
