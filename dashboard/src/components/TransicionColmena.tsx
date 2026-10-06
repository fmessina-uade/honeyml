export type Fase = 'quieta' | 'inicial' | 'cerrando' | 'abriendo';

// Cuánto tarda el velo en cubrir la sección vieja y cuánto en descubrir la nueva. Son los mismos
// tiempos del sitio público, así pasar de uno al otro se siente igual.
export const CIERRE_MS = 480;
export const APERTURA_MS = 600;

/**
 * La transición entre secciones: el logo de la marca girando sobre un velo que cubre la sección
 * vieja mientras se cambia y se retira sobre la nueva. Es el mismo cargador del sitio público,
 * con el mismo archivo del logo. En la primera carga el velo arranca ya cubriendo, así no se llega
 * a ver la pantalla sin datos.
 */
export default function TransicionColmena({ fase }: { fase: Fase }) {
  if (fase === 'quieta') return null;
  const clase =
    fase === 'cerrando' ? 'colmena-velo-entra' : fase === 'abriendo' ? 'colmena-velo-sale' : '';

  return (
    <div
      className={`fixed inset-0 z-[200] flex items-center justify-center ${clase}`}
      style={{ background: 'var(--abyss-black)' }}
      aria-hidden="true"
    >
      <div className="colmena-giro">
        <img
          src="/logo.png"
          width={120}
          height={120}
          alt=""
          aria-hidden="true"
          className="select-none"
          draggable={false}
        />
      </div>
    </div>
  );
}
