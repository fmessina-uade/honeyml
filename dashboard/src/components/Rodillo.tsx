import { useState } from 'react';
import { useQuieto } from '../lib/useQuieto';

/**
 * Una cifra que, cuando cambia, gira como un cuentakilómetros: solo los dígitos que cambiaron, de
 * derecha a izquierda, con un destello ámbar. Trabaja sobre el texto ya formateado, así sirve igual
 * para "24,3 M" que para "1.234.567" sin saber de separadores ni de idiomas.
 *
 * La primera vez no anima: la cifra entra con la sección. Gira con los refrescos, que es cuando
 * llegó algo nuevo.
 */
export default function Rodillo({ texto }: { texto: string }) {
  const quieto = useQuieto();
  const [estado, setEstado] = useState({ texto, viejo: texto, vuelta: 0 });
  if (estado.texto !== texto) {
    setEstado({ texto, viejo: estado.texto, vuelta: estado.vuelta + 1 });
  }

  const nuevo = [...texto];
  // Alineados por la derecha: si la cifra suma un dígito, las unidades siguen con las unidades.
  const corrimiento = estado.viejo.length - nuevo.length;
  return (
    <span className="rodillo" aria-label={texto}>
      {nuevo.map((c, i) => {
        const antes = estado.viejo[i + corrimiento];
        const gira = !quieto && estado.vuelta > 0 && /\d/.test(c) && antes !== c;
        return (
          <span
            key={gira ? `${i}-${estado.vuelta}` : i}
            className="rodillo-celda"
            data-gira={gira ? 'si' : undefined}
            style={gira ? ({ '--orden': nuevo.length - i } as React.CSSProperties) : undefined}
            aria-hidden
          >
            {gira && antes && <span className="rodillo-viejo">{antes}</span>}
            {c}
          </span>
        );
      })}
    </span>
  );
}
