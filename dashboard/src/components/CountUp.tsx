import { useEffect, useState } from 'react';
import { useInView } from '../lib/useInView';

interface CountUpProps {
  end: number;
  decimals?: number;
  suffix?: string;
  duration?: number;
  className?: string;
}

/**
 * Contador animado. La misma curva que el sitio público, con separador de miles: el panel muestra
 * cifras en millones y sin separadores no se leen.
 */
export default function CountUp({
  end,
  decimals = 0,
  suffix = '',
  duration = 1800,
  className,
}: CountUpProps) {
  const { ref, inView } = useInView<HTMLSpanElement>(0.4);
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!inView) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
      setValue(end);
      return;
    }
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      // se acota de los dos lados: requestAnimationFrame puede devolver una marca anterior al
      // performance.now() de arriba, y una t negativa dibuja un número negativo
      const t = Math.min(1, Math.max(0, (now - start) / duration));
      setValue(end * (1 - Math.pow(1 - t, 3)));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, end, duration]);

  return (
    <span ref={ref} className={className}>
      {value.toLocaleString('es-AR', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
      {suffix}
    </span>
  );
}
