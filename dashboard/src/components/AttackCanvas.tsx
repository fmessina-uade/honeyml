import { useEffect, useRef } from 'react';

interface Props {
  /** Conteos diarios de eventos, del más viejo al más nuevo. Define cuántos nodos aparecen y a qué
   *  velocidad se mueven. */
  intensity: number[];
}

interface Node {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
}

const LINK_DIST = 74;

/**
 * Textura de fondo del encabezado de sección, armada con la propia captura.
 *
 * Adaptada del canvas de partículas del sitio público, con una diferencia que importa: la cantidad
 * de nodos y la velocidad de deriva salen del volumen diario real, así que un período movido se ve
 * movido. Es decoración que no puede contradecir a los datos, porque está hecha de ellos.
 *
 * Dibuja a devicePixelRatio, se pausa cuando queda fuera de pantalla, y directamente no corre con
 * prefers-reduced-motion ni en modo captura.
 */
export default function AttackCanvas({ intensity }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const frozen = document.documentElement.dataset.capture === 'on';

    const peak = Math.max(...intensity, 1);
    const recent = intensity.slice(-14);
    const level = recent.reduce((a, b) => a + b, 0) / (recent.length || 1) / peak;
    // entre 18 y 46 nodos: suficiente para leerse como una red, nunca tanto como para ser ruido
    const count = Math.round(18 + level * 28);

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let nodes: Node[] = [];

    const resize = () => {
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.22,
        vy: (Math.random() - 0.5) * 0.22,
        r: 0.9 + Math.random() * 1.3,
      }));
    };
    resize();
    window.addEventListener('resize', resize);

    let raf = 0;
    let running = true;

    const draw = (step: boolean) => {
      const w = canvas.width / dpr;
      const h = canvas.height / dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      if (step) {
        for (const nd of nodes) {
          nd.x += nd.vx;
          nd.y += nd.vy;
          if (nd.x < 0 || nd.x > w) nd.vx *= -1;
          if (nd.y < 0 || nd.y > h) nd.vy *= -1;
        }
      }

      ctx.strokeStyle = 'rgba(212,134,10,0.16)';
      ctx.lineWidth = 1;
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const d2 = dx * dx + dy * dy;
          if (d2 < LINK_DIST * LINK_DIST) {
            ctx.globalAlpha = 1 - Math.sqrt(d2) / LINK_DIST;
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.stroke();
          }
        }
      }
      ctx.globalAlpha = 1;

      ctx.fillStyle = 'rgba(212,134,10,0.5)';
      for (const nd of nodes) {
        ctx.beginPath();
        ctx.arc(nd.x, nd.y, nd.r, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    if (reduced || frozen) {
      // un solo cuadro estático: la textura sigue estando, no se mueve nada
      draw(false);
      return () => window.removeEventListener('resize', resize);
    }

    const frame = () => {
      if (!running) return;
      draw(true);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    const io = new IntersectionObserver(([entry]) => {
      running = entry.isIntersecting;
      if (running) raf = requestAnimationFrame(frame);
      else cancelAnimationFrame(raf);
    });
    io.observe(canvas);

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      io.disconnect();
      window.removeEventListener('resize', resize);
    };
  }, [intensity]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="absolute inset-0 w-full h-full pointer-events-none"
      style={{
        maskImage: 'linear-gradient(to bottom, #000 10%, transparent 95%)',
        WebkitMaskImage: 'linear-gradient(to bottom, #000 10%, transparent 95%)',
      }}
    />
  );
}
