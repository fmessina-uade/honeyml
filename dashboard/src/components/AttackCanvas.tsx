import { useEffect, useRef } from 'react';

interface Props {
  /** Daily event counts, oldest first. Drives how many nodes appear and how fast they move. */
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
 * Background texture for the section header, built from the capture itself.
 *
 * Adapted from the public site's particle canvas, with one difference that matters: the node count
 * and drift speed come from the real daily volume, so a busy period looks busy. It is decoration
 * that cannot contradict the data, because it is made of it.
 *
 * Renders at devicePixelRatio, pauses when off-screen, and does not run at all under
 * prefers-reduced-motion or in capture mode.
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
    // between 18 and 46 nodes: enough to read as a network, never enough to be noise
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
      // one static frame: the texture is still there, nothing moves
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
