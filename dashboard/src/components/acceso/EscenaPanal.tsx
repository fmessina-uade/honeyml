import { useEffect, useRef } from 'react';
import { useQuieto } from '../../lib/useQuieto';

/**
 * El fondo del ingreso: un panal que recibe ataques. Cada ataque cruza la pantalla como una estela
 * gris, cae en una celda que se enciende en ámbar (quedó capturado) y, un momento después, un pulso
 * teal la une al núcleo (el motor lo clasificó). Uno de cada siete llega en coral: los críticos.
 *
 * Va en canvas y no en SVG porque en un teléfono cientos de nodos animados por el DOM traban el
 * desplazamiento. La retícula se dibuja una vez en una capa aparte y cada cuadro solo pinta lo que
 * se mueve. Con movimiento reducido o en modo captura queda un cuadro fijo, con algunas celdas
 * encendidas.
 */

interface Celda {
  x: number;
  y: number;
  /** Cercanía al núcleo, de 0 a 1: los ataques caen más cerca de él que lejos. */
  peso: number;
}

interface Ataque {
  desde: [number, number];
  celda: Celda;
  inicio: number;
  duracion: number;
  critico: boolean;
}

interface Captura {
  celda: Celda;
  inicio: number;
  critico: boolean;
}

interface Colores {
  fondo: string;
  tinta: string;
  ambar: string;
  teal: string;
  coral: string;
  pizarra: string;
  claro: boolean;
}

const VIDA_CAPTURA_MS = 3400;
const DEMORA_CLASIFICACION_MS = 520;

function leerColores(): Colores {
  const css = getComputedStyle(document.documentElement);
  const v = (nombre: string) => css.getPropertyValue(nombre).trim();
  return {
    fondo: `rgb(${v('--fondo').split(' ').join(',')})`,
    tinta: v('--tinta').split(' ').join(','),
    ambar: v('--honey-amber'),
    teal: v('--neural-teal'),
    coral: v('--agent-coral'),
    pizarra: v('--ghost-slate'),
    claro: document.documentElement.dataset.tema === 'claro',
  };
}

function hexagono(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i;
    const px = x + r * Math.cos(a);
    const py = y + r * Math.sin(a);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
}

// Un generador con semilla: el cuadro fijo sale igual cada vez, y las capturas de pantalla también.
function semilla(s: number) {
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

/** Dónde queda el núcleo según la forma de la pantalla: lejos de la tarjeta del formulario. */
function nucleo(w: number, h: number): [number, number] {
  if (w < 700) return [w * 0.64, h * 0.2];
  if (w / h < 1.02) return [w * 0.5, h * 0.24];
  return [w * 0.3, h * 0.42];
}

export default function EscenaPanal({ etiqueta }: { etiqueta: string }) {
  const lienzo = useRef<HTMLCanvasElement>(null);
  const quieto = useQuieto();

  useEffect(() => {
    const canvas = lienzo.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const capa = document.createElement('canvas');
    const capaCtx = capa.getContext('2d');
    if (!capaCtx) return;

    let colores = leerColores();
    let ancho = 0;
    let alto = 0;
    let radio = 40;
    let centro: [number, number] = [0, 0];
    let celdas: Celda[] = [];
    let ataques: Ataque[] = [];
    let capturas: Captura[] = [];
    let proximo = 0;
    let marco = 0;
    const azar = semilla(11);

    const armar = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, ancho < 700 ? 1.5 : 2);
      ancho = canvas.clientWidth;
      alto = canvas.clientHeight;
      for (const c of [canvas, capa]) {
        c.width = Math.round(ancho * dpr);
        c.height = Math.round(alto * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      capaCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

      radio = Math.max(30, Math.min(58, Math.min(ancho, alto) / 13));
      centro = nucleo(ancho, alto);
      const dx = radio * 1.5;
      const dy = radio * Math.sqrt(3);
      const alcance = Math.hypot(ancho, alto);
      celdas = [];
      for (let col = -1; col * dx < ancho + radio; col++) {
        for (let fila = -1; fila * dy < alto + radio; fila++) {
          const x = col * dx;
          const y = fila * dy + (col % 2 ? dy / 2 : 0);
          const d = Math.hypot(x - centro[0], y - centro[1]);
          celdas.push({ x, y, peso: 1 - Math.min(1, d / (alcance * 0.55)) });
        }
      }
      pintarReticula();
    };

    const pintarReticula = () => {
      const c = capaCtx;
      c.clearRect(0, 0, ancho, alto);
      c.fillStyle = colores.fondo;
      c.fillRect(0, 0, ancho, alto);

      // El resplandor del núcleo, que es lo único iluminado de la escena quieta.
      const brillo = c.createRadialGradient(...centro, 0, ...centro, radio * 7);
      brillo.addColorStop(0, `${colores.ambar}${colores.claro ? '22' : '2e'}`);
      brillo.addColorStop(1, `${colores.ambar}00`);
      c.fillStyle = brillo;
      c.fillRect(0, 0, ancho, alto);

      const azarFijo = semilla(7);
      c.lineWidth = 1;
      for (const celda of celdas) {
        const cerca = celda.peso;
        c.strokeStyle = `rgba(${colores.tinta},${(colores.claro ? 0.07 : 0.05) + cerca * 0.09})`;
        hexagono(c, celda.x, celda.y, radio * 0.94);
        c.stroke();
        // Los nodos del logo en algunos vértices: coral, teal y pizarra.
        if (azarFijo() < 0.16) {
          const a = (Math.PI / 3) * Math.floor(azarFijo() * 6);
          const tono = [colores.coral, colores.teal, colores.pizarra][Math.floor(azarFijo() * 3)];
          c.fillStyle = tono;
          c.globalAlpha = 0.28 + cerca * 0.4;
          c.beginPath();
          c.arc(
            celda.x + radio * 0.94 * Math.cos(a),
            celda.y + radio * 0.94 * Math.sin(a),
            1.6 + cerca * 1.2,
            0,
            Math.PI * 2,
          );
          c.fill();
          c.globalAlpha = 1;
        }
      }

      // El núcleo es el logo: el hexágono de la celda central relleno en ámbar al 42 %, con el
      // hexágono interior y su punto.
      const [nx, ny] = centro;
      c.fillStyle = colores.ambar;
      c.globalAlpha = 0.42;
      hexagono(c, nx, ny, radio * 0.94);
      c.fill();
      c.globalAlpha = 1;
      c.strokeStyle = colores.ambar;
      c.lineWidth = 2;
      hexagono(c, nx, ny, radio * 0.94);
      c.stroke();
      c.fillStyle = colores.ambar;
      hexagono(c, nx, ny, radio * 0.32);
      c.fill();
    };

    const elegirCelda = (): Celda => {
      // Más probable cerca del núcleo, pero cualquiera puede recibir uno.
      for (let i = 0; i < 12; i++) {
        const c = celdas[Math.floor(azar() * celdas.length)];
        if (
          c &&
          azar() < 0.15 + c.peso * 0.85 &&
          Math.hypot(c.x - centro[0], c.y - centro[1]) > radio
        )
          return c;
      }
      return celdas[Math.floor(azar() * celdas.length)];
    };

    const lanzar = (ahora: number) => {
      const celda = elegirCelda();
      // Entran por cualquier borde, con algo más de peso arriba y a la derecha.
      const borde = azar();
      const margen = 60;
      const desde: [number, number] =
        borde < 0.38
          ? [azar() * ancho, -margen]
          : borde < 0.7
            ? [ancho + margen, azar() * alto * 0.8]
            : borde < 0.88
              ? [-margen, azar() * alto]
              : [azar() * ancho, alto + margen];
      const distancia = Math.hypot(celda.x - desde[0], celda.y - desde[1]);
      ataques.push({
        desde,
        celda,
        inicio: ahora,
        duracion: Math.max(700, distancia / (0.75 + azar() * 0.5)),
        critico: azar() < 1 / 7,
      });
    };

    const suave = (t: number) => 1 - Math.pow(1 - t, 3);

    const cuadro = (ahora: number) => {
      ctx.drawImage(capa, 0, 0, ancho, alto);

      if (ahora >= proximo) {
        lanzar(ahora);
        proximo = ahora + 260 + azar() * 620;
      }

      // Las celdas capturadas: el ámbar sube rápido y se apaga despacio; la clasificación llega
      // después como un borde teal y una línea punteada hasta el núcleo.
      capturas = capturas.filter((c) => ahora - c.inicio < VIDA_CAPTURA_MS);
      for (const c of capturas) {
        const t = (ahora - c.inicio) / VIDA_CAPTURA_MS;
        const encendido = t < 0.08 ? t / 0.08 : 1 - (t - 0.08) / 0.92;
        ctx.fillStyle = colores.ambar;
        ctx.globalAlpha = 0.42 * encendido;
        hexagono(ctx, c.celda.x, c.celda.y, radio * 0.94);
        ctx.fill();

        const onda = Math.min(1, (ahora - c.inicio) / 700);
        if (onda < 1) {
          ctx.globalAlpha = (1 - onda) * 0.8;
          ctx.strokeStyle = c.critico ? colores.coral : colores.ambar;
          ctx.lineWidth = 1.6;
          hexagono(ctx, c.celda.x, c.celda.y, radio * (0.94 + onda * 0.7));
          ctx.stroke();
        }

        const clasificada = ahora - c.inicio - DEMORA_CLASIFICACION_MS;
        if (clasificada > 0) {
          const tc = Math.min(1, clasificada / 1100);
          ctx.globalAlpha = (1 - tc) * 0.9;
          ctx.strokeStyle = colores.teal;
          ctx.lineWidth = 1.8;
          hexagono(ctx, c.celda.x, c.celda.y, radio * 0.94);
          ctx.stroke();
          ctx.setLineDash([3, 5]);
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.moveTo(c.celda.x, c.celda.y);
          const largo = suave(Math.min(1, clasificada / 500));
          ctx.lineTo(
            c.celda.x + (centro[0] - c.celda.x) * largo,
            c.celda.y + (centro[1] - c.celda.y) * largo,
          );
          ctx.stroke();
          ctx.setLineDash([]);
        }
        ctx.globalAlpha = 1;
      }

      // Las estelas: una cabeza y una cola que se desvanece hacia atrás.
      const siguen: Ataque[] = [];
      for (const a of ataques) {
        const t = (ahora - a.inicio) / a.duracion;
        if (t >= 1) {
          capturas.push({ celda: a.celda, inicio: ahora, critico: a.critico });
          continue;
        }
        siguen.push(a);
        const p = suave(t);
        const x = a.desde[0] + (a.celda.x - a.desde[0]) * p;
        const y = a.desde[1] + (a.celda.y - a.desde[1]) * p;
        const ang = Math.atan2(a.celda.y - a.desde[1], a.celda.x - a.desde[0]);
        const cola = Math.min(150, 40 + t * 220);
        const tono = a.critico ? colores.coral : colores.pizarra;
        const estela = ctx.createLinearGradient(
          x - Math.cos(ang) * cola,
          y - Math.sin(ang) * cola,
          x,
          y,
        );
        estela.addColorStop(0, `${tono}00`);
        estela.addColorStop(1, `${tono}cc`);
        ctx.strokeStyle = estela;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.moveTo(x - Math.cos(ang) * cola, y - Math.sin(ang) * cola);
        ctx.lineTo(x, y);
        ctx.stroke();
        ctx.fillStyle = a.critico ? colores.coral : `rgba(${colores.tinta},0.85)`;
        ctx.beginPath();
        ctx.arc(x, y, 2, 0, Math.PI * 2);
        ctx.fill();
      }
      ataques = siguen;
      marco = requestAnimationFrame(cuadro);
    };

    const fijo = () => {
      ctx.drawImage(capa, 0, 0, ancho, alto);
      const azarFijo = semilla(3);
      ctx.fillStyle = colores.ambar;
      for (let i = 0; i < 9; i++) {
        const c = celdas[Math.floor(azarFijo() * celdas.length)];
        ctx.globalAlpha = 0.12 + c.peso * 0.3;
        hexagono(ctx, c.x, c.y, radio * 0.94);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    };

    const arrancar = () => {
      cancelAnimationFrame(marco);
      armar();
      // La retícula se pinta ya, sin esperar el primer cuadro: así el fondo nunca aparece vacío.
      ctx.drawImage(capa, 0, 0, ancho, alto);
      if (quieto) fijo();
      else marco = requestAnimationFrame(cuadro);
    };

    arrancar();
    const observador = new ResizeObserver(arrancar);
    observador.observe(canvas);
    const tema = new MutationObserver(() => {
      colores = leerColores();
      arrancar();
    });
    tema.observe(document.documentElement, { attributes: true, attributeFilter: ['data-tema'] });
    // Con la pestaña oculta no se dibuja; al volver, se retoma sin una ráfaga de atrasados.
    const alCambiarVisibilidad = () => {
      if (document.hidden) cancelAnimationFrame(marco);
      else if (!quieto) {
        ataques = [];
        capturas = [];
        marco = requestAnimationFrame(cuadro);
      }
    };
    document.addEventListener('visibilitychange', alCambiarVisibilidad);
    return () => {
      cancelAnimationFrame(marco);
      observador.disconnect();
      tema.disconnect();
      document.removeEventListener('visibilitychange', alCambiarVisibilidad);
    };
  }, [quieto]);

  return <canvas ref={lienzo} className="escena-panal" role="img" aria-label={etiqueta} />;
}
