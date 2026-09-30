import { MousePointerClick, ShieldCheck, Workflow, X } from 'lucide-react';
import { useI18n } from '../../lib/i18n';
import { Hexagono } from '../Instrumento';

const ICONOS = [Workflow, MousePointerClick, ShieldCheck];
const COLORES = ['var(--agent-coral)', 'var(--honey-amber)', 'var(--neural-teal)'];

/** Los tres pasos de la sección, para quien la abre por primera vez. Se cierra y queda cerrada. */
export default function Guia({ onCerrar }: { onCerrar: () => void }) {
  const { t } = useI18n();
  const g = t.triage.guide;
  return (
    <div className="panel section-in p-4">
      <div className="flex items-start justify-between gap-3">
        <span className="rotulo">{g.title}</span>
        <button
          onClick={onCerrar}
          className="flex items-center gap-1 text-[11px] text-white/50 hover:text-white/85 transition -mt-0.5"
        >
          {g.ok}
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <ol className="grid md:grid-cols-3 gap-3 mt-3">
        {g.steps.map((paso, i) => {
          const Icono = ICONOS[i];
          return (
            <li key={paso.title} className="flex items-start gap-3">
              <Hexagono color={COLORES[i]}>
                <Icono className="w-3.5 h-3.5" />
              </Hexagono>
              <div>
                <div className="text-[12.5px] text-white/85">
                  <span className="font-data text-white/35 mr-1.5">{i + 1}</span>
                  {paso.title}
                </div>
                <p className="text-[11px] text-white/50 leading-relaxed mt-0.5">{paso.text}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
