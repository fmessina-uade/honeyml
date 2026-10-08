import { useEffect, useState } from 'react';
import { RotateCw } from 'lucide-react';
import { useI18n } from '../../lib/i18n';

/**
 * Cuándo se actualizaron por última vez las cifras en vivo, y el botón para pedirlas ya. El panel
 * igual las vuelve a pedir solo cada minuto; esto es para no esperar en una demostración.
 */
export default function Refresco({
  actualizado,
  refrescando,
  onRefrescar,
}: {
  actualizado: number | null;
  refrescando: boolean;
  onRefrescar: () => void;
}) {
  const { t } = useI18n();
  const [ahora, setAhora] = useState(Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setAhora(Date.now()), 5000);
    return () => window.clearInterval(id);
  }, []);

  const segundos = actualizado ? Math.max(0, Math.round((ahora - actualizado) / 1000)) : 0;
  return (
    <button
      onClick={onRefrescar}
      disabled={refrescando}
      className="refresco"
      title={t.refresco.actualizar}
      aria-label={`${t.refresco.hace(segundos)}. ${t.refresco.actualizar}`}
      data-capture-toggle
    >
      <RotateCw className="w-3.5 h-3.5" data-girando={refrescando ? 'si' : undefined} aria-hidden />
      <span>{t.refresco.hace(segundos)}</span>
    </button>
  );
}
