import { useEffect, useRef, useState, type ReactNode } from 'react';

interface Anchor {
  x: number;
  y: number;
}

/**
 * Cursor-following tooltip for the charts.
 *
 * The native `title` attribute was the obvious shortcut and the wrong one: it waits a second
 * before appearing, cannot be styled to match the surface, and cannot show more than a line.
 * Readings here need units, a share of the total and a per-sensor split, so it is worth the
 * component. Renders in a fixed layer and flips sides near the viewport edge.
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
    // flip to the other side of the cursor when the tooltip would leave the viewport
    const dx = at.x + 14 + r.width > window.innerWidth ? -r.width - 14 : 14;
    const dy = at.y - 8 + r.height > window.innerHeight ? -r.height + 8 : -8;
    setOffset({ dx, dy });
  }, [content, at.x, at.y]);

  if (!content) return null;

  return (
    <div
      ref={ref}
      className="fixed z-50 pointer-events-none rounded-lg px-3 py-2 ring-1 ring-white/10
                 bg-[#161b22]/95 backdrop-blur-sm shadow-xl shadow-black/40"
      style={{ left: at.x + offset.dx, top: at.y + offset.dy }}
    >
      {content}
    </div>
  );
}
