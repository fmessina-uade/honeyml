import type { ResumenTriaje } from '../lib/api';
import { hora, n } from '../lib/format';
import { useI18n } from '../lib/i18n';

type Minuto = NonNullable<ResumenTriaje['actividad']['por_minuto']>[number];

/**
 * El pulso del motor: cuántas decisiones tomó en cada minuto de la última hora, separando las que
 * copió de una conducta ya decidida de las que razonó con el modelo. El minuto de la derecha es el
 * que está corriendo, así que las decisiones nuevas se ven crecer ahí.
 *
 * Los minutos vacíos se dibujan como una marca baja y no se omiten: el motor trabaja a ráfagas, y un
 * gráfico que juntara dos ráfagas separadas por media hora de silencio contaría otra cosa.
 */
export default function Latido({
  serie,
  alto = 56,
  compacto = false,
}: {
  serie: Minuto[];
  alto?: number;
  compacto?: boolean;
}) {
  const { t } = useI18n();
  const e = t.triage.engine;
  const maximo = Math.max(...serie.map((m) => m.decisiones), 1);
  const total = serie.reduce((a, m) => a + m.decisiones, 0);
  const razonadas = serie.reduce((a, m) => a + (m.decisiones - m.copiadas), 0);

  return (
    <div className="w-full min-w-0">
      {!compacto && (
        <div className="flex items-baseline justify-between gap-3 flex-wrap mb-2">
          <span className="rotulo">{e.pulseTitle}</span>
          <span className="flex items-center gap-3 text-[10px] text-white/45">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-sm bg-[var(--neural-teal)]" />
              {e.pulseCopied}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-sm bg-[var(--agent-coral)]" />
              {e.pulseReasoned}
            </span>
            <span className="font-data text-white/35">{e.pulseTotals(n(total), n(razonadas))}</span>
          </span>
        </div>
      )}
      <div
        className="flex items-end gap-[2px]"
        style={{ height: alto }}
        role="img"
        aria-label={e.pulseTitle}
      >
        {serie.map((m, i) => {
          const ultimo = i === serie.length - 1;
          const h = m.decisiones ? Math.max((m.decisiones / maximo) * 100, 8) : 0;
          const propias = m.decisiones - m.copiadas;
          return (
            <div
              key={m.minuto ?? i}
              className="flex-1 h-full flex flex-col justify-end"
              title={`${hora(m.minuto).slice(0, 5)}: ${e.pulseMinute(m.decisiones, m.copiadas)}`}
            >
              {m.decisiones ? (
                <div
                  className={`w-full rounded-[2px] overflow-hidden flex flex-col-reverse transition-all duration-700 ${
                    ultimo ? 'latido-ahora' : ''
                  }`}
                  style={{ height: `${h}%` }}
                >
                  <div
                    className="w-full"
                    style={{
                      height: `${(m.copiadas / m.decisiones) * 100}%`,
                      background: 'var(--neural-teal)',
                      opacity: 0.75,
                    }}
                  />
                  {propias > 0 && (
                    <div
                      className="w-full"
                      style={{
                        height: `${(propias / m.decisiones) * 100}%`,
                        background: 'var(--agent-coral)',
                      }}
                    />
                  )}
                </div>
              ) : (
                <div className="w-full h-[2px] rounded-full bg-white/10" />
              )}
            </div>
          );
        })}
      </div>
      {!compacto && (
        <div className="flex justify-between font-data text-[9px] text-white/30 mt-1">
          <span>{hora(serie[0]?.minuto).slice(0, 5)}</span>
          <span>{e.pulseNow}</span>
        </div>
      )}
    </div>
  );
}
