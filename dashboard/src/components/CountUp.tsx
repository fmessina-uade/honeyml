import { useEffect, useRef, useState } from 'react';
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
 *
 * Cuando la cifra cambia porque el panel se refrescó, cuenta desde la que estaba mostrando y no
 * desde cero: lo nuevo se ve sumarse, con un destello mientras sube.
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
  const mostrada = useRef(0);
  const [sube, setSube] = useState(false);

  useEffect(() => {
    // En modo captura y con movimiento reducido la cifra aparece final: una captura tomada a mitad
    // de la cuenta mostraría un número que no es el dato.
    if (quieto) {
      mostrada.current = end;
      setValue(end);
      return;
    }
    if (!inView) return;
    const desde = mostrada.current;
    // la primera cuenta arranca de cero y dura lo de siempre; un refresco suma rápido lo que llegó
    const largo = desde === 0 ? duration : Math.min(duration, 1200);
    setSube(desde > 0 && end > desde);
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      // se acota de los dos lados: requestAnimationFrame puede devolver una marca anterior al
      // performance.now() de arriba, y una t negativa dibuja un número negativo
      const t = Math.min(1, Math.max(0, (now - start) / largo));
      mostrada.current = desde + (end - desde) * (1 - Math.pow(1 - t, 3));
      setValue(mostrada.current);
      if (t < 1) raf = requestAnimationFrame(tick);
      else setSube(false);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, end, duration, quieto]);

  return (
    <span ref={ref} className={className} data-sube={sube ? 'si' : undefined}>
      {dec(value, decimals)}
      {suffix}
    </span>
  );
}
