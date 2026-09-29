import { useEffect, useRef, useState, type CSSProperties } from 'react';
import rough from 'roughjs';
import { useInView } from '../lib/useInView';
import { useQuieto } from '../lib/useQuieto';

// Las posiciones van en porcentaje del contenedor, así una anotación sigue a su dato aunque el
// gráfico cambie de ancho.
export type Trazo =
  | { tipo: 'elipse'; x: number; y: number; ancho: number; alto: number }
  | { tipo: 'flecha'; desde: [number, number]; hasta: [number, number]; curva?: number }
  | { tipo: 'subrayado'; x1: number; x2: number; y: number };

export interface Nota {
  x: number;
  y: number;
  texto: string;
  alinear?: 'izquierda' | 'derecha' | 'centro';
  ancho?: number;
}

// Cuánto tarda en dibujarse cada trazo, y cuánto se espera entre uno y otro.
const DIBUJO_MS = 700;
const ENTRE_TRAZOS_MS = 260;

/**
 * La capa que un profesor dibujaría sobre el pizarrón: círculos, flechas y subrayados a mano
 * alzada, con notas manuscritas que dicen qué mirar.
 *
 * Se dibuja sola la primera vez que el gráfico entra en pantalla, trazo por trazo. La semilla de
 * cada trazo es fija, así el mismo dato se anota siempre igual y las capturas se repiten. En modo
 * captura y con movimiento reducido aparece terminada.
 */
export default function ManoAlzada({
  trazos,
  notas,
  color = '#ffb38f',
  acotar = true,
}: {
  trazos: Trazo[];
  notas: Nota[];
  color?: string;
  /** Si las notas se acotan al ancho del contenedor. Sobre un elemento chico, como una palabra,
   *  conviene dejarlas salir. */
  acotar?: boolean;
}) {
  const { ref, inView } = useInView<HTMLDivElement>(0.35);
  const quieto = useQuieto();
  const lienzo = useRef<SVGSVGElement | null>(null);
  const [tam, setTam] = useState({ w: 0, h: 0 });
  // Se dibuja trazo por trazo una sola vez. Si después cambia el ancho, los trazos se rehacen a la
  // medida nueva pero aparecen enteros: repetir la animación en cada ajuste distrae.
  const yaDibujado = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const medir = () => setTam({ w: el.clientWidth, h: el.clientHeight });
    medir();
    const observador = new ResizeObserver(medir);
    observador.observe(el);
    return () => observador.disconnect();
  }, [ref]);

  // Los trazos llegan como un arreglo nuevo en cada render del gráfico (basta pasar el puntero por
  // una barra para que se vuelva a dibujar el tooltip). Se comparan por contenido, así la capa solo
  // se rehace cuando cambia de verdad lo que anota.
  const clave = JSON.stringify(trazos);

  useEffect(() => {
    const svg = lienzo.current;
    if (!svg || !tam.w || !inView) return;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const rc = rough.svg(svg);
    const px = (x: number) => (x / 100) * tam.w;
    const py = (y: number) => (y / 100) * tam.h;
    const estilo = { stroke: color, strokeWidth: 1.7, roughness: 1.5, bowing: 1.4 };
    const animar = !quieto && !yaDibujado.current;

    trazos.forEach((trazo, i) => {
      const opciones = { ...estilo, seed: 11 + i * 7 };
      const grupo = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      if (trazo.tipo === 'elipse') {
        grupo.appendChild(
          rc.ellipse(px(trazo.x), py(trazo.y), px(trazo.ancho), py(trazo.alto), opciones),
        );
      } else if (trazo.tipo === 'subrayado') {
        const medio = (trazo.x1 + trazo.x2) / 2;
        grupo.appendChild(
          rc.curve(
            [
              [px(trazo.x1), py(trazo.y)],
              [px(medio), py(trazo.y) + 3],
              [px(trazo.x2), py(trazo.y) - 1],
            ],
            opciones,
          ),
        );
      } else {
        const [x1, y1] = [px(trazo.desde[0]), py(trazo.desde[1])];
        const [x2, y2] = [px(trazo.hasta[0]), py(trazo.hasta[1])];
        const curva = trazo.curva ?? 0.25;
        const medio: [number, number] = [
          (x1 + x2) / 2 - (y2 - y1) * curva,
          (y1 + y2) / 2 + (x2 - x1) * curva,
        ];
        grupo.appendChild(rc.curve([[x1, y1], medio, [x2, y2]], opciones));
        // La punta sigue la dirección con que la curva llega al destino.
        const angulo = Math.atan2(y2 - medio[1], x2 - medio[0]);
        const punta = (desvio: number): [number, number] => [
          x2 - 10 * Math.cos(angulo + desvio),
          y2 - 10 * Math.sin(angulo + desvio),
        ];
        grupo.appendChild(rc.linearPath([punta(0.45), [x2, y2], punta(-0.45)], opciones));
      }
      svg.appendChild(grupo);

      if (!animar) return;
      // Cada trazo aparece como si lo estuviera dibujando alguien: se revela su largo de a poco.
      grupo.querySelectorAll('path').forEach((camino) => {
        const largo = camino.getTotalLength();
        camino.style.strokeDasharray = `${largo}`;
        camino.style.strokeDashoffset = `${largo}`;
        camino.style.transition = `stroke-dashoffset ${DIBUJO_MS}ms ease-out ${
          i * ENTRE_TRAZOS_MS
        }ms`;
      });
    });

    if (!animar) return;
    let interno = 0;
    const marco = requestAnimationFrame(() => {
      interno = requestAnimationFrame(() => {
        // Se marca recién acá, cuando la animación arranca de verdad: en desarrollo el efecto
        // corre dos veces seguidas y la primera se cancela antes de llegar a este punto.
        yaDibujado.current = true;
        svg.querySelectorAll('path').forEach((camino) => {
          camino.style.strokeDashoffset = '0';
        });
      });
    });
    return () => {
      cancelAnimationFrame(marco);
      cancelAnimationFrame(interno);
    };
  }, [clave, tam, inView, quieto, color]);

  const demora = trazos.length * ENTRE_TRAZOS_MS + DIBUJO_MS / 2;
  // En un teléfono la letra baja un punto, para que la nota ocupe menos renglones sobre el dato.
  const angosto = tam.w > 0 && tam.w < 480;

  return (
    <div ref={ref} className="absolute inset-0 pointer-events-none" aria-hidden>
      <svg
        ref={lienzo}
        width={tam.w}
        height={tam.h}
        className="absolute inset-0 overflow-visible"
      />
      {notas.map((nota) => {
        const alinear = nota.alinear ?? 'izquierda';
        // Cada nota se ancla del lado que corresponde y su ancho se acota al lugar que le queda
        // hasta el borde: en un contenedor angosto el texto pasa a otro renglón en vez de salirse.
        const x = Math.min(Math.max(nota.x, 0), 100);
        const lugar =
          alinear === 'derecha'
            ? (x / 100) * tam.w
            : alinear === 'centro'
              ? (Math.min(x, 100 - x) / 50) * tam.w
              : ((100 - x) / 100) * tam.w;
        const ancho = acotar
          ? Math.max(Math.min(nota.ancho ?? 260, lugar - 4), 90)
          : (nota.ancho ?? 260);
        const estilo: CSSProperties = {
          top: `${nota.y}%`,
          width: 'max-content',
          maxWidth: `${ancho}px`,
          color,
          transform: `${alinear === 'centro' ? 'translateX(-50%) ' : ''}rotate(-2deg)`,
          transformOrigin: alinear === 'derecha' ? 'right top' : 'left top',
          textAlign: alinear === 'derecha' ? 'right' : alinear === 'centro' ? 'center' : 'left',
          opacity: inView || quieto ? 1 : 0,
          transition: quieto ? undefined : `opacity 600ms ease ${demora}ms`,
          ...(alinear === 'derecha' ? { right: `${100 - x}%` } : { left: `${x}%` }),
        };
        return (
          <div
            key={nota.texto}
            className={`absolute font-mano leading-[1.05] ${angosto ? 'text-[15px]' : 'text-[17px]'}`}
            style={estilo}
          >
            {nota.texto}
          </div>
        );
      })}
    </div>
  );
}
