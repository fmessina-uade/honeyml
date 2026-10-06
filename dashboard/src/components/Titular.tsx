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
