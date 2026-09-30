import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useI18n } from '../lib/i18n';

/**
 * Lo que comparten el diálogo y el panel lateral: se cierran con Escape o tocando afuera, llevan el
 * foco adentro al abrirse y lo devuelven adonde estaba al cerrarse. Van en un portal sobre el cuerpo
 * del documento, así ningún contenedor con desborde oculto los recorta.
 */
function useSuperpuesto(abierto: boolean, onCerrar: () => void) {
  const caja = useRef<HTMLDivElement | null>(null);
  const cerrar = useRef(onCerrar);
  cerrar.current = onCerrar;

  useEffect(() => {
    if (!abierto) return;
    const previo = document.activeElement as HTMLElement | null;
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === 'Escape') cerrar.current();
    };
    document.addEventListener('keydown', alTeclear);
    // El primer control con intención de foco, o la caja misma.
    const primero = caja.current?.querySelector<HTMLElement>('[data-foco-inicial]');
    (primero ?? caja.current)?.focus();
    return () => {
      document.removeEventListener('keydown', alTeclear);
      previo?.focus?.();
    };
  }, [abierto]);

  return caja;
}

function Encabezado({
  id,
  titulo,
  onCerrar,
}: {
  id: string;
  titulo: ReactNode;
  onCerrar: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-3 border-b border-white/5">
      <h2 id={id} className="titulo text-[14px] leading-snug">
        {titulo}
      </h2>
      <button
        onClick={onCerrar}
        aria-label={t.triage.detail.close}
        className="shrink-0 flex items-center justify-center w-8 h-8 -mr-2 -mt-1 rounded-lg text-white/50 hover:text-white hover:bg-white/5 transition"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

/** Un diálogo centrado; en el teléfono sube desde abajo, a lo ancho. */
export function Modal({
  abierto,
  onCerrar,
  titulo,
  children,
  pie,
}: {
  abierto: boolean;
  onCerrar: () => void;
  titulo: ReactNode;
  children: ReactNode;
  pie?: ReactNode;
}) {
  const id = useId();
  const caja = useSuperpuesto(abierto, onCerrar);
  if (!abierto) return null;
  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby={id}
    >
      <button
        aria-hidden
        tabIndex={-1}
        onClick={onCerrar}
        className="absolute inset-0 bg-black/60 menu-velo cursor-default"
      />
      <div
        ref={caja}
        tabIndex={-1}
        className="modal-cuerpo relative w-full sm:max-w-xl max-h-[92dvh] flex flex-col bg-elevada rounded-t-2xl sm:rounded-2xl ring-1 ring-white/10 shadow-2xl shadow-black/40 outline-none"
      >
        <Encabezado id={id} titulo={titulo} onCerrar={onCerrar} />
        <div className="flex-1 overflow-y-auto thin-scroll px-5 py-4">{children}</div>
        {pie && <div className="px-5 py-3 border-t border-white/5">{pie}</div>}
      </div>
    </div>,
    document.body,
  );
}

/** Un panel que entra desde la derecha; en el teléfono ocupa la pantalla entera. */
export function Cajon({
  abierto,
  onCerrar,
  titulo,
  children,
  pie,
}: {
  abierto: boolean;
  onCerrar: () => void;
  titulo: ReactNode;
  children: ReactNode;
  pie?: ReactNode;
}) {
  const id = useId();
  const caja = useSuperpuesto(abierto, onCerrar);
  if (!abierto) return null;
  return createPortal(
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-labelledby={id}>
      <button
        aria-hidden
        tabIndex={-1}
        onClick={onCerrar}
        className="absolute inset-0 bg-black/45 menu-velo cursor-default"
      />
      <div
        ref={caja}
        tabIndex={-1}
        className="cajon-cuerpo absolute inset-y-0 right-0 w-full sm:w-[520px] flex flex-col bg-superficie ring-1 ring-white/10 shadow-2xl shadow-black/40 outline-none"
      >
        <Encabezado id={id} titulo={titulo} onCerrar={onCerrar} />
        <div className="flex-1 overflow-y-auto thin-scroll px-5 py-4">{children}</div>
        {pie && <div className="px-5 py-3 border-t border-white/5 bg-superficie">{pie}</div>}
      </div>
    </div>,
    document.body,
  );
}
