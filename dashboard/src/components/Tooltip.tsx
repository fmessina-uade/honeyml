import { useEffect, useRef, useState, type ReactNode } from 'react';

interface Anchor {
  x: number;
  y: number;
}

/**
 * Tooltip que sigue al cursor, para los gráficos.
 *
 * El atributo nativo `title` era el atajo obvio y el equivocado: espera un segundo antes de
 * aparecer, no se puede estilar para que combine con la superficie, y no muestra más de una línea.
 * Las lecturas de acá necesitan unidades, la proporción sobre el total y el desglose por sensor,
 * así que el componente vale la pena. Se dibuja en una capa fija y se da vuelta cerca del borde.
 */
export function useTooltip() {
  const [content, setContent] = useState<ReactNode>(null);
  const [at, setAt] = useState<Anchor>({ x: 0, y: 0 });

  const show = (e: { clientX: number; clientY: number }, node: ReactNode) => {
    setAt({ x: e.clientX, y: e.clientY });
    setContent(node);
  };
  const hide = () => setContent(null);

  return { content, at, show, hide };
}

export default function Tooltip({ content, at }: { content: ReactNode; at: Anchor }) {
  const ref = useRef<HTMLDivElement>(null);
  const [offset, setOffset] = useState({ dx: 14, dy: -8 });

  useEffect(() => {
    const el = ref.current;
    if (!el || !content) return;
    const r = el.getBoundingClientRect();
    // pasa al otro lado del cursor cuando el tooltip se saldría de la pantalla
    const dx = at.x + 14 + r.width > window.innerWidth ? -r.width - 14 : 14;
    const dy = at.y - 8 + r.height > window.innerHeight ? -r.height + 8 : -8;
    setOffset({ dx, dy });
  }, [content, at.x, at.y]);

  if (!content) return null;

  return (
    <div
      ref={ref}
      className="fixed z-50 pointer-events-none rounded-lg px-3 py-2 ring-1 ring-white/10
                 bg-elevada/95 backdrop-blur-sm shadow-xl shadow-black/40"
      style={{ left: at.x + offset.dx, top: at.y + offset.dy }}
    >
      {content}
    </div>
  );
}
