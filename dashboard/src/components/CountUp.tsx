import { useEffect, useState } from 'react';
import { useInView } from '../lib/useInView';
import { dec } from '../lib/format';
import { useQuieto } from '../lib/useQuieto';

interface CountUpProps {
  end: number;
  decimals?: number;
  suffix?: string;
  duration?: number;
  className?: string;
}

/**
 * Contador animado. La misma curva que el sitio público, con separador de miles en el idioma
 * elegido: el panel muestra cifras en millones y sin separadores no se leen.
 */
export default function CountUp({
  end,
  decimals = 0,
  suffix = '',
  duration = 1800,
  className,
}: CountUpProps) {
  const { ref, inView } = useInView<HTMLSpanElement>(0.4);
  const quieto = useQuieto();
  const [value, setValue] = useState(0);

  useEffect(() => {
    // En modo captura y con movimiento reducido la cifra aparece final: una captura tomada a mitad
    // de la cuenta mostraría un número que no es el dato.
    if (quieto) {
      setValue(end);
      return;
    }
    if (!inView) return;
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
  }, [inView, end, duration, quieto]);

  return (
    <span ref={ref} className={className}>
      {dec(value, decimals)}
      {suffix}
    </span>
  );
}
