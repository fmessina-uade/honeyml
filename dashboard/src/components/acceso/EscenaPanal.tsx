import { useEffect, useRef, type RefObject } from 'react';
import { useQuieto } from '../../lib/useQuieto';

/**
 * El fondo del ingreso: un panal con varios honeypots, cada uno con el servicio que emula, y el
 * tráfico que les llega. Cada ataque cruza la pantalla como una estela gris hasta un honeypot, que lo
 * captura: se enciende en ámbar, suma uno a su cuenta y, un momento después, un pulso teal dice que
 * el motor lo clasificó. Uno de cada siete llega en coral: los críticos.
 *
 * Los servicios y cuánto tráfico recibe cada uno siguen el reparto real de la captura: la mayoría
 * va a SSH. Va en canvas y no en SVG porque en un teléfono cientos de nodos animados por el DOM
 * traban el desplazamiento; la retícula se dibuja una vez en una capa aparte y cada cuadro pinta
 * solo lo que se mueve. Con movimiento reducido o en modo captura queda un cuadro fijo.
 */

interface Honeypot {
  x: number;
  y: number;
  servicio: string;
  peso: number;
  capturas: number;
}

interface Ataque {
  desde: [number, number];
  destino: Honeypot;
  inicio: number;
  duracion: number;
  critico: boolean;
}

interface Captura {
  honeypot: Honeypot;
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

const SERVICIOS: { servicio: string; peso: number }[] = [
  { servicio: 'SSH :22', peso: 0.5 },
  { servicio: 'SMB :445', peso: 0.16 },
  { servicio: 'Telnet :23', peso: 0.14 },
  { servicio: 'HTTP :80', peso: 0.08 },
  { servicio: 'MySQL :3306', peso: 0.05 },
  { servicio: 'FTP :21', peso: 0.04 },
  { servicio: 'MSSQL :1433', peso: 0.03 },
];

const VIDA_CAPTURA_MS = 1800;
const DEMORA_CLASIFICACION_MS = 520;
// Lo que ocupa cada honeypot por debajo de su celda: el servicio, la cuenta y un respiro antes del
// texto que tenga abajo. El relleno superior del titular en el teléfono (index.css) cuenta con
// estas medidas.
const PIE_DEL_HONEYPOT = 44;
const AIRE_BAJO_LOS_CONTROLES = 4;

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

// Un generador con semilla: la escena sale igual cada vez, y las capturas de pantalla también.
function semilla(s: number) {
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

/**
 * La zona donde van los honeypots, según la forma de la pantalla: lejos de la tarjeta del formulario
 * y por encima del titular. Devuelve [x0, y0, x1, y1] y cuántos entran.
 *
 * En el teléfono el titular va en el flujo de la página y su altura depende del idioma y del ancho,
 * así que una proporción fija de la pantalla lo pisa. Ahí la zona es la franja medida entre los
 * controles de arriba y el comienzo del texto: la celda entera queda debajo de los controles, y el
 * servicio y la cuenta de cada honeypot, por encima del texto.
 */
function zona(
  w: number,
  h: number,
  franja: [number, number] | null,
  radio: number,
): [number, number, number, number, number] {
  if (w < 700) {
    if (!franja) return [w * 0.12, h * 0.05, w * 0.88, h * 0.36, 3];
    const [arriba, abajo] = franja;
    return [
      w * 0.12,
      arriba + AIRE_BAJO_LOS_CONTROLES + radio * 0.94,
      w * 0.88,
      abajo - radio - PIE_DEL_HONEYPOT,
      3,
    ];
  }
  if (w / h < 1.02) return [w * 0.1, h * 0.04, w * 0.9, h * 0.16, 4];
  const tarjeta = Math.min(560, Math.max(380, w * 0.38)) + 28;
  return [w * 0.08, h * 0.12, w - tarjeta - w * 0.07, h * 0.6, 6];
}

export default function EscenaPanal({
  etiqueta,
  controles,
  texto,
}: {
  etiqueta: string;
  controles?: RefObject<HTMLElement>;
  texto?: RefObject<HTMLElement>;
}) {
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
    let honeypots: Honeypot[] = [];
    let ataques: Ataque[] = [];
    let capturas: Captura[] = [];
    let proximo = 0;
    let marco = 0;
    let desfase = 0;
    const azar = semilla(11);

    // La franja libre entre el borde inferior de los controles y el comienzo del texto. Se mide
    // con offsetTop, que da la posición en reposo: no cambia al desplazar la página, como pasa
    // cuando se abre el teclado, ni con la animación de entrada.
    const franjaLibre = (): [number, number] | null => {
      const arriba = controles?.current;
      const abajo = texto?.current;
      if (!arriba || !abajo) return null;
      const relleno = parseFloat(getComputedStyle(abajo).paddingTop) || 0;
      return [arriba.offsetTop + arriba.offsetHeight, abajo.offsetTop + relleno];
    };

    const armar = () => {
      ancho = canvas.clientWidth;
      alto = canvas.clientHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, ancho < 700 ? 1.5 : 2);
      for (const c of [canvas, capa]) {
        c.width = Math.round(ancho * dpr);
        c.height = Math.round(alto * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      capaCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      radio = Math.max(28, Math.min(52, Math.min(ancho, alto) / 14));

      // Los honeypots caen en celdas de la retícula, separados entre sí, en la zona libre.
      const dx = radio * 1.5;
      const dy = radio * Math.sqrt(3);
      const franja = ancho < 700 ? franjaLibre() : null;
      const [x0, y0, x1, y1, cuantos] = zona(ancho, alto, franja, radio);
      // Con la franja medida, la retícula se corre en vertical hasta que una fila de celdas cae
      // justo en su borde superior. Si no, la fila más cercana podría quedar afuera y no entraría
      // ningún honeypot aunque la franja tenga el alto de uno.
      desfase = franja ? ((y0 % dy) + dy) % dy : 0;
      const celdas: [number, number][] = [];
      for (let col = -1; col * dx < ancho + radio; col++) {
        for (let fila = -1; fila * dy < alto + radio; fila++) {
          const x = col * dx;
          const y = fila * dy + (col % 2 ? dy / 2 : 0) + desfase;
          if (x >= x0 && x <= x1 && y >= y0 - 0.5 && y <= y1) celdas.push([x, y]);
        }
      }
      const elegir = semilla(23);
      const elegidas: [number, number][] = [];
      for (let intento = 0; intento < 400 && elegidas.length < cuantos; intento++) {
        const c = celdas[Math.floor(elegir() * celdas.length)];
        if (c && elegidas.every((e) => Math.hypot(e[0] - c[0], e[1] - c[1]) > radio * 2.9)) {
          elegidas.push(c);
        }
      }
      const servicios = SERVICIOS.slice(0, elegidas.length);
      const total = servicios.reduce((s, x) => s + x.peso, 0);
      const anteriores = new Map(honeypots.map((h) => [h.servicio, h.capturas]));
      honeypots = elegidas.map(([x, y], i) => ({
        x,
        y,
        servicio: servicios[i].servicio,
        peso: servicios[i].peso / total,
        capturas: anteriores.get(servicios[i].servicio) ?? 0,
      }));
      ataques = [];
      capturas = [];
      pintarReticula(dx, dy);
    };

    const pintarReticula = (dx: number, dy: number) => {
      const c = capaCtx;
      c.clearRect(0, 0, ancho, alto);
      c.fillStyle = colores.fondo;
      c.fillRect(0, 0, ancho, alto);

      const azarFijo = semilla(7);
      c.lineWidth = 1;
      for (let col = -1; col * dx < ancho + radio; col++) {
        for (let fila = -1; fila * dy < alto + radio; fila++) {
          const x = col * dx;
          const y = fila * dy + (col % 2 ? dy / 2 : 0) + desfase;
          const cerca = Math.max(
            0,
            ...honeypots.map((h) => 1 - Math.min(1, Math.hypot(h.x - x, h.y - y) / (radio * 5))),
          );
          c.strokeStyle = `rgba(${colores.tinta},${(colores.claro ? 0.07 : 0.05) + cerca * 0.07})`;
          hexagono(c, x, y, radio * 0.94);
          c.stroke();
          // Los nodos del logo en algunos vértices: coral, teal y pizarra.
          if (azarFijo() < 0.14) {
            const a = (Math.PI / 3) * Math.floor(azarFijo() * 6);
            c.fillStyle = [colores.coral, colores.teal, colores.pizarra][
              Math.floor(azarFijo() * 3)
            ];
            c.globalAlpha = 0.25 + cerca * 0.35;
            c.beginPath();
            c.arc(
              x + radio * 0.94 * Math.cos(a),
              y + radio * 0.94 * Math.sin(a),
              1.6,
              0,
              Math.PI * 2,
            );
            c.fill();
            c.globalAlpha = 1;
          }
        }
      }

      // Cada honeypot es una celda con la marca del logo adentro y el servicio que emula debajo.
      c.font = `500 ${ancho < 700 ? 10 : 11}px 'JetBrains Mono', monospace`;
      c.textAlign = 'center';
      for (const h of honeypots) {
        c.strokeStyle = colores.ambar;
        c.globalAlpha = 0.55;
        c.lineWidth = 1.4;
        hexagono(c, h.x, h.y, radio * 0.94);
        c.stroke();
        c.globalAlpha = colores.claro ? 0.22 : 0.3;
        c.fillStyle = colores.ambar;
        hexagono(c, h.x, h.y, radio * 0.6);
        c.fill();
        c.globalAlpha = 0.85;
        hexagono(c, h.x, h.y, radio * 0.22);
        c.fill();
        c.globalAlpha = 1;
        c.fillStyle = `rgba(${colores.tinta},0.55)`;
        c.fillText(h.servicio, h.x, h.y + radio + 16);
      }
    };

    const elegirDestino = (): Honeypot => {
      let r = azar();
      for (const h of honeypots) {
        r -= h.peso;
        if (r <= 0) return h;
      }
      return honeypots[0];
    };

    const lanzar = (ahora: number) => {
      if (honeypots.length === 0) return;
      const destino = elegirDestino();
      const borde = azar();
      const margen = 60;
      const desde: [number, number] =
        borde < 0.36
          ? [azar() * ancho, -margen]
          : borde < 0.7
            ? [ancho + margen, azar() * alto * 0.85]
            : borde < 0.9
              ? [-margen, azar() * alto]
              : [azar() * ancho, alto + margen];
      const distancia = Math.hypot(destino.x - desde[0], destino.y - desde[1]);
      ataques.push({
        desde,
        destino,
        inicio: ahora,
        duracion: Math.max(650, distancia / (0.8 + azar() * 0.6)),
        critico: azar() < 1 / 7,
      });
    };

    const suave = (t: number) => 1 - Math.pow(1 - t, 3);

    const cuadro = (ahora: number) => {
      ctx.drawImage(capa, 0, 0, ancho, alto);

      if (ahora >= proximo) {
        lanzar(ahora);
        proximo = ahora + 140 + azar() * 360;
      }

      // Las estelas: una cola que se desvanece hacia atrás y una cabeza.
      const siguen: Ataque[] = [];
      for (const a of ataques) {
        const t = (ahora - a.inicio) / a.duracion;
        if (t >= 1) {
          a.destino.capturas += 1;
          capturas.push({ honeypot: a.destino, inicio: ahora, critico: a.critico });
          continue;
        }
        siguen.push(a);
        const p = suave(t);
        const x = a.desde[0] + (a.destino.x - a.desde[0]) * p;
        const y = a.desde[1] + (a.destino.y - a.desde[1]) * p;
        const ang = Math.atan2(a.destino.y - a.desde[1], a.destino.x - a.desde[0]);
        const cola = Math.min(160, 40 + t * 240);
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

      // La captura: el honeypot se enciende, una onda sale de él, sube un +1, y después llega el
      // pulso teal de la clasificación.
      capturas = capturas.filter((c) => ahora - c.inicio < VIDA_CAPTURA_MS);
      ctx.textAlign = 'center';
      for (const c of capturas) {
        const { x, y } = c.honeypot;
        const t = (ahora - c.inicio) / VIDA_CAPTURA_MS;
        const tono = c.critico ? colores.coral : colores.ambar;

        ctx.fillStyle = tono;
        ctx.globalAlpha = 0.5 * (1 - t);
        hexagono(ctx, x, y, radio * 0.6);
        ctx.fill();

        const onda = Math.min(1, (ahora - c.inicio) / 650);
        if (onda < 1) {
          ctx.globalAlpha = (1 - onda) * 0.85;
          ctx.strokeStyle = tono;
          ctx.lineWidth = 1.6;
          hexagono(ctx, x, y, radio * (0.94 + onda * 0.55));
          ctx.stroke();
        }

        const clasificada = ahora - c.inicio - DEMORA_CLASIFICACION_MS;
        if (clasificada > 0) {
          ctx.globalAlpha = Math.max(0, 1 - clasificada / 900) * 0.9;
          ctx.strokeStyle = colores.teal;
          ctx.lineWidth = 2;
          hexagono(ctx, x, y, radio * 0.94);
          ctx.stroke();
        }

        ctx.globalAlpha = Math.max(0, 1 - t * 1.3);
        ctx.fillStyle = tono;
        ctx.font = `600 ${ancho < 700 ? 11 : 12}px 'JetBrains Mono', monospace`;
        ctx.fillText('+1', x + radio * 0.75, y - radio * 0.7 - t * 22);
        ctx.globalAlpha = 1;
      }

      // La cuenta de cada honeypot, debajo de su servicio.
      ctx.font = `500 ${ancho < 700 ? 10 : 11}px 'JetBrains Mono', monospace`;
      ctx.fillStyle = colores.ambar;
      for (const h of honeypots) {
        if (h.capturas > 0) ctx.fillText(h.capturas.toLocaleString(), h.x, h.y + radio + 30);
      }

      marco = requestAnimationFrame(cuadro);
    };

    const arrancar = () => {
      cancelAnimationFrame(marco);
      armar();
      // La retícula se pinta ya, sin esperar el primer cuadro: así el fondo nunca aparece vacío.
      ctx.drawImage(capa, 0, 0, ancho, alto);
      if (!quieto) marco = requestAnimationFrame(cuadro);
    };

    arrancar();
    const observador = new ResizeObserver(arrancar);
    observador.observe(canvas);
    // El titular cambia de alto cuando llega su tipografía o cambia el idioma, y en el teléfono eso
    // mueve el borde inferior de la franja.
    if (texto?.current) observador.observe(texto.current);
    const tema = new MutationObserver(() => {
      colores = leerColores();
      arrancar();
    });
    tema.observe(document.documentElement, { attributes: true, attributeFilter: ['data-tema'] });
    // Con la pestaña oculta no se dibuja; al volver se retoma sin una ráfaga de atrasados.
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
  }, [quieto, controles, texto]);

  return <canvas ref={lienzo} className="escena-panal" role="img" aria-label={etiqueta} />;
}
