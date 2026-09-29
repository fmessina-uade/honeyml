import type { MouseEvent, ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

/** El hexágono de marca, como insignia de cada indicador. */
export function Hexagono({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span className="relative inline-flex w-7 h-7 items-center justify-center shrink-0">
      <svg viewBox="0 0 28 28" className="absolute inset-0 w-full h-full" aria-hidden>
        <polygon
          points="14,1.5 25,7.75 25,20.25 14,26.5 3,20.25 3,7.75"
          style={{ fill: 'rgba(255,255,255,0.03)', stroke: color, strokeOpacity: 0.7 }}
          strokeWidth={1.2}
        />
      </svg>
      <span className="relative" style={{ color }}>
        {children}
      </span>
    </span>
  );
}

/**
 * La tarjeta de una cifra, igual en todas las secciones: insignia, rótulo, cifra y una línea que la
 * explica. El filo de arriba y el resplandor llevan el color de lo que se mide.
 */
export function Indicador({
  icono: Icono,
  rotulo,
  valor,
  sub,
  color,
  onClick,
  onMouseMove,
  onMouseLeave,
  resaltado,
}: {
  icono: LucideIcon;
  rotulo: string;
  valor: ReactNode;
  sub?: ReactNode;
  color: string;
  onClick?: () => void;
  onMouseMove?: (e: MouseEvent) => void;
  onMouseLeave?: () => void;
  resaltado?: boolean;
}) {
  const contenido = (
    <>
      <span className="tile-glow" style={{ background: color }} />
      <span
        className="absolute inset-x-0 top-0 h-px"
        style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }}
      />
      <div className="relative">
        <div className="flex items-center gap-2.5">
          <Hexagono color={color}>
            <Icono className="w-3.5 h-3.5" />
          </Hexagono>
          <span className="rotulo">{rotulo}</span>
        </div>
        <div className="cifra mt-3" style={resaltado ? { color } : undefined}>
          {valor}
        </div>
        {sub && <div className="text-[10px] text-white/45 mt-1 leading-relaxed">{sub}</div>}
      </div>
    </>
  );
  const clase = 'panel tile overflow-hidden p-4 h-full w-full text-left';
  const estilo = resaltado
    ? { boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${color} 45%, transparent)` }
    : undefined;

  if (onClick) {
    return (
      <button
        onClick={onClick}
        className={`${clase} transition hover:bg-white/[0.05]`}
        style={estilo}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
      >
        {contenido}
      </button>
    );
  }
  return (
    <div
      className={`${clase} cursor-default`}
      style={estilo}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
    >
      {contenido}
    </div>
  );
}
