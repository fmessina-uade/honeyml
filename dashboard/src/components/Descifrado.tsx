import { useEffect, useState } from 'react';
import { useQuieto } from '../lib/useQuieto';

const GLIFOS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&*+=/<>';
const DURACION_MS = 560;

/**
 * Un texto que aparece descifrándose: cada letra pasa por glifos al azar hasta asentarse, de
 * izquierda a derecha. Va sobre la letra monoespaciada de los títulos, así el ancho no salta
 * mientras dura. En modo captura y con movimiento reducido se muestra directo.
 */
export default function Descifrado({ texto }: { texto: string }) {
  const quieto = useQuieto();
  const [visible, setVisible] = useState(texto);

  useEffect(() => {
    if (quieto) {
      setVisible(texto);
      return;
    }
    const inicio = performance.now();
    let marco = 0;
    const paso = (ahora: number) => {
      const avance = Math.min(1, Math.max(0, (ahora - inicio) / DURACION_MS));
      const fijas = Math.floor(avance * texto.length);
      setVisible(
        [...texto]
          .map((c, i) =>
            i < fijas || c === ' ' ? c : GLIFOS[Math.floor(Math.random() * GLIFOS.length)],
          )
          .join(''),
      );
      if (avance < 1) marco = requestAnimationFrame(paso);
    };
    marco = requestAnimationFrame(paso);
    return () => cancelAnimationFrame(marco);
  }, [texto, quieto]);

  return (
    <>
      <span className="sr-only">{texto}</span>
      <span aria-hidden>{visible}</span>
    </>
  );
}
