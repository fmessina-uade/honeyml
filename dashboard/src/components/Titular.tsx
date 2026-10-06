/**
 * El titular de una sección: cada palabra sube detrás de su máscara, una tras otra, y la última va
 * en ámbar. Marca dónde empieza cada pantalla.
 */
export default function Titular({ texto }: { texto: string }) {
  const palabras = texto.split(' ');
  const ultima = palabras.length - 1;
  return (
    <h1 className="titular" aria-label={texto}>
      {palabras.map((p, i) => (
        <span key={i} aria-hidden>
          <span className="titular-mascara">
            {i === ultima ? (
              <em style={{ '--d': `${0.08 + i * 0.09}s` } as React.CSSProperties}>{p}</em>
            ) : (
              <span style={{ '--d': `${0.08 + i * 0.09}s` } as React.CSSProperties}>{p}</span>
            )}
          </span>
          {i < ultima && ' '}
        </span>
      ))}
    </h1>
  );
}

/**
 * Las palabras de un titular de presentación, cada una subiendo detrás de su máscara. Lo usan las
 * secciones que dibujan su propio encabezado, cada una con su tamaño y su disposición.
 */
export function Palabras({ texto, ultimaEn }: { texto: string; ultimaEn?: string }) {
  const palabras = texto.split(' ');
  const ultima = palabras.length - 1;
  return (
    <span aria-label={texto}>
      {palabras.map((p, i) => (
        <span key={i} aria-hidden>
          <span className="titular-mascara">
            <span
              style={
                {
                  '--d': `${0.1 + i * 0.09}s`,
                  color: i === ultima ? ultimaEn : undefined,
                } as React.CSSProperties
              }
            >
              {p}
            </span>
          </span>
          {i < ultima && ' '}
        </span>
      ))}
    </span>
  );
}
