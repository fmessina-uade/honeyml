import { useEffect, useRef, useState } from 'react';

/**
 * El ancho real de un contenedor, actualizado cuando cambia. Los gráficos que dibujan en píxeles lo
 * usan para rehacerse a la medida en lugar de estirar un viewBox, que deforma el texto.
 */
export function useAncho<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [ancho, setAncho] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const medir = () => setAncho(el.clientWidth);
    medir();
    const observador = new ResizeObserver(medir);
    observador.observe(el);
    return () => observador.disconnect();
  }, []);

  return { ref, ancho };
}
