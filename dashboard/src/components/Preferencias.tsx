import { Camera, Monitor, Moon, Sun } from 'lucide-react';
import { useI18n } from '../lib/i18n';
import { useTema, type Preferencia } from '../lib/tema';
import LangToggle from './LangToggle';

const OPCIONES: { valor: Preferencia; icono: typeof Sun }[] = [
  { valor: 'sistema', icono: Monitor },
  { valor: 'claro', icono: Sun },
  { valor: 'oscuro', icono: Moon },
];

/**
 * Lo que cada quien ajusta del panel para sí: idioma, tema y modo captura. Viven en el navegador de
 * quien mira y no en su cuenta, así que también se pueden elegir antes de ingresar.
 *
 * `enLinea` las pone en una sola fila; ahí el tema muestra solo íconos y el nombre queda en el
 * título de cada botón. Sin `onCapture` no aparece el modo captura, que en el ingreso no tiene uso.
 */
export default function Preferencias({
  capture = false,
  onCapture,
  enLinea = false,
}: {
  capture?: boolean;
  onCapture?: () => void;
  enLinea?: boolean;
}) {
  const { t } = useI18n();
  const { preferencia, elegir } = useTema();

  const captura = onCapture && (
    <button
      onClick={onCapture}
      title={t.capture.hint}
      aria-label={t.capture.on}
      aria-pressed={capture}
      /* El modo captura apaga los eventos de puntero de toda la página para que el cursor no
         deje un estado de hover en la captura. Este botón queda exceptuado, porque si no, no
         habría forma de volver a apagarlo. */
      data-capture-toggle
      className={`flex items-center justify-center rounded-full p-1.5 transition ${
        capture
          ? 'bg-[var(--honey-amber)]/20 text-[var(--honey-amber)] ring-1 ring-[var(--honey-amber)]/40'
          : 'bg-white/5 text-white/40 ring-1 ring-white/10 hover:text-white/75'
      }`}
    >
      <Camera className="w-3.5 h-3.5" />
    </button>
  );

  const tema = (
    <div
      className="flex items-center gap-0.5 rounded-full bg-white/5 ring-1 ring-white/10 p-0.5 w-fit"
      role="group"
      aria-label={t.theme.title}
    >
      {OPCIONES.map(({ valor, icono: Icono }) => (
        <button
          key={valor}
          onClick={() => elegir(valor)}
          aria-pressed={preferencia === valor}
          title={t.theme[valor]}
          className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] transition ${
            preferencia === valor
              ? 'bg-white/10 text-white/90'
              : 'text-white/45 hover:text-white/75'
          }`}
        >
          <Icono className="w-3 h-3" />
          <span className={preferencia === valor && !enLinea ? '' : 'sr-only'}>
            {t.theme[valor]}
          </span>
        </button>
      ))}
    </div>
  );

  if (enLinea) {
    return (
      <div className="flex items-center gap-2">
        <LangToggle />
        {tema}
        {captura}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center gap-2">
        <LangToggle />
        {captura}
      </div>
      {tema}
    </div>
  );
}
