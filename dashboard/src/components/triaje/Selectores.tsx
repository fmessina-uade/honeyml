import { useI18n } from '../../lib/i18n';
import { tacticColor } from '../sections/SessionReplay';
import { OBSERVED } from '../sections/MitreMatrix';
import { SEVERIDADES, colorDeSeveridad } from './comunes';

const indice = (k: string) => SEVERIDADES.indexOf(k as (typeof SEVERIDADES)[number]);

/**
 * Los cinco niveles para elegir uno. Los que quedan fuera del rango que la evidencia sostiene se
 * atenúan pero se pueden elegir: el rango es una guía y la última palabra es de quien revisa.
 *
 * `marcada` pone una etiqueta sobre un nivel. El veredicto común marca el del motor; la revisión a
 * ciegas no marca nada, porque esa etiqueta es justo lo que no tiene que verse.
 */
export function SelectorSeveridad({
  valor,
  onElegir,
  piso,
  techo,
  rotulo,
  marcada,
  etiqueta,
}: {
  valor: string;
  onElegir: (s: string) => void;
  piso: string;
  techo: string;
  rotulo: string;
  marcada?: string | null;
  etiqueta?: string;
}) {
  const { t } = useI18n();
  const nivel = (k: string) => t.severities[k as keyof typeof t.severities] ?? k;
  const dentro = (k: string) => indice(k) >= indice(piso) && indice(k) <= indice(techo);
  return (
    <div className="grid grid-cols-3 sm:grid-cols-5 gap-2" role="radiogroup" aria-label={rotulo}>
      {SEVERIDADES.map((s) => {
        const color = colorDeSeveridad(s);
        const elegida = valor === s;
        const fuera = !dentro(s);
        return (
          <button
            key={s}
            role="radio"
            aria-checked={elegida}
            onClick={() => onElegir(s)}
            title={fuera ? t.triage.modal.outOfRange : undefined}
            className="relative rounded-lg px-2 py-2 text-[11.5px] transition first-letter:uppercase"
            style={{
              color: elegida ? color : 'rgb(var(--tinta) / 0.7)',
              background: elegida
                ? `color-mix(in srgb, ${color} 14%, transparent)`
                : 'rgb(var(--tinta) / 0.03)',
              boxShadow: `inset 0 0 0 ${elegida ? 1.5 : 1}px ${
                elegida ? color : 'rgb(var(--tinta) / 0.1)'
              }`,
              opacity: fuera && !elegida ? 0.55 : 1,
            }}
          >
            <span
              className="inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle"
              style={{ background: color }}
            />
            {nivel(s)}
            {marcada === s && etiqueta && (
              <span className="absolute -top-2 right-1.5 font-data text-[8.5px] px-1 rounded bg-elevada text-white/50 ring-1 ring-white/10">
                {etiqueta}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Las tácticas que el señuelo observa, más "ninguna", cada una con lo que significa. El valor
 * vacío es "ninguna"; `null`, que todavía no se eligió.
 */
export function SelectorTactica({
  valor,
  onElegir,
  rotulo,
  tacticName,
  marcada,
  etiqueta,
}: {
  valor: string | null;
  onElegir: (tactica: string) => void;
  rotulo: string;
  tacticName: (key: string) => string;
  marcada?: string | null;
  etiqueta?: string;
}) {
  const { t } = useI18n();
  const m = t.triage.modal;
  return (
    <div className="grid sm:grid-cols-2 gap-2" role="radiogroup" aria-label={rotulo}>
      {[...OBSERVED, ''].map((tac) => {
        const color = tac ? tacticColor(tac) : 'var(--ghost-slate)';
        const elegida = valor === tac;
        return (
          <button
            key={tac || 'ninguna'}
            role="radio"
            aria-checked={elegida}
            onClick={() => onElegir(tac)}
            className="relative flex items-start gap-2.5 rounded-lg px-3 py-2.5 text-left transition"
            style={{
              background: elegida
                ? `color-mix(in srgb, ${color} 12%, transparent)`
                : 'rgb(var(--tinta) / 0.03)',
              boxShadow: `inset 0 0 0 ${elegida ? 1.5 : 1}px ${
                elegida ? color : 'rgb(var(--tinta) / 0.1)'
              }`,
            }}
          >
            <span className="w-2 h-2 rounded-full shrink-0 mt-1" style={{ background: color }} />
            <span className="min-w-0">
              <span
                className="block text-[12px]"
                style={{ color: elegida ? color : 'rgb(var(--tinta) / 0.85)' }}
              >
                {tac ? tacticName(tac) : m.none}
              </span>
              <span className="block text-[10.5px] text-white/45 leading-snug mt-0.5">
                {tac ? t.tactics[tac as keyof typeof t.tactics]?.meaning : m.noneHint}
              </span>
            </span>
            {marcada !== undefined && (marcada ?? '') === tac && etiqueta && (
              <span className="absolute -top-2 right-2 font-data text-[8.5px] px-1 rounded bg-elevada text-white/50 ring-1 ring-white/10">
                {etiqueta}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
