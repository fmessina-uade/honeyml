import { useEffect, useState } from 'react';

function leerQuieto(): boolean {
  return (
    document.documentElement.dataset.capture === 'on' ||
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

/**
 * Si hay que dibujar quieto: en modo captura o con movimiento reducido. Se entera si cambia, porque
 * el modo captura se prende y se apaga con la sección abierta.
 */
export function useQuieto(): boolean {
  const [quieto, setQuieto] = useState(leerQuieto);
  useEffect(() => {
    const actualizar = () => setQuieto(leerQuieto());
    const observador = new MutationObserver(actualizar);
    observador.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-capture'],
    });
    const consulta = window.matchMedia('(prefers-reduced-motion: reduce)');
    consulta.addEventListener('change', actualizar);
    return () => {
      observador.disconnect();
      consulta.removeEventListener('change', actualizar);
    };
  }, []);
  return quieto;
}
