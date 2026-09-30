import type { WeeklyRhythm } from '../lib/api';
import Tooltip, { useTooltip } from './Tooltip';
import { dec, n } from '../lib/format';
import { useI18n } from '../lib/i18n';

/**
 * Día de la semana contra hora del día, 168 celdas.
 *
 * La curva horaria sola ya dice que el tráfico es automático, pero en veinticuatro barras se lee
 * como un gráfico que casualmente quedó parejo, y el lector tiene que creerle a la conclusión.
 * Desplegada sobre una semana entera, la afirmación pasa a ser algo que puede comprobar: cualquier
 * cosa movida por personas se enciende de lunes a viernes entre las nueve y las seis, y se apaga de
 * noche y los fines de semana.
 *
 * Los tres números de abajo están porque la grilla sola invita al ojo a encontrar formas en el
 * ruido. Dicen cuánto suman las celdas, así la lectura no depende de impresiones.
 */

const HORAS_OFICINA = { desde: 9, hasta: 18 };
const HORAS_MADRUGADA = { desde: 0, hasta: 6 };

/**
 * Rampa de dos colores sobre la paleta del proyecto: verde azulado para las horas tranquilas,
 * ámbar en el medio, coral en el pico.
 *
 * Con un solo tono a distintas opacidades, todas las celdas quedaban del mismo color y el lector
 * terminaba comparando matices de un mismo tono, que es algo que el ojo hace mal. Tres anclas le
 * dan identidad propia a cada banda y a la vez mantienen la luminosidad percibida subiendo con el
 * valor, así una celda más oscura siempre significa menos. Es la propiedad que una escala arcoíris
 * rompe al poner un amarillo brillante al lado de un azul oscuro.
 */
const RAMPA: [number, number, number][] = [
  [0, 184, 148], // --neural-teal
  [212, 134, 10], // --honey-amber
  [255, 107, 53], // --agent-coral
];

function color(v: number, max: number): string {
  if (max <= 0) return 'rgb(var(--tinta) / 0.03)';
  // Raíz cuadrada y no lineal: con la escala lineal, un pico aplasta al resto y la grilla queda
  // casi toda del mismo tono, que es justamente lo que se quiere poder comparar.
  const t = Math.min(1, Math.sqrt(Math.max(0, v) / max));

  const tramo = t * (RAMPA.length - 1);
  const i = Math.min(RAMPA.length - 2, Math.floor(tramo));
  const f = tramo - i;
  const [r1, g1, b1] = RAMPA[i];
  const [r2, g2, b2] = RAMPA[i + 1];
  const mezcla = (a: number, b: number) => Math.round(a + (b - a) * f);

  // La opacidad acompaña al tono: sin eso, las celdas bajas quedan de un verde sólido que pesa
  // tanto como el pico y la grilla deja de tener relieve.
  const alfa = 0.14 + t * 0.78;
  return `rgba(${mezcla(r1, r2)}, ${mezcla(g1, g2)}, ${mezcla(b1, b2)}, ${alfa.toFixed(3)})`;
}

function promedio(m: number[][], dias: number[], desde: number, hasta: number): number {
  let suma = 0;
  let celdas = 0;
  for (const d of dias) {
    for (let h = desde; h < hasta; h++) {
      suma += m[d][h];
      celdas++;
    }
  }
  return celdas ? suma / celdas : 0;
}

export default function WeekHeatmap({ data }: { data: WeeklyRhythm }) {
  const { t } = useI18n();
  const tip = useTooltip();

  const m = data.average;
  const max = Math.max(...m.flat(), 1);

  const laborables = [0, 1, 2, 3, 4];
  const finde = [5, 6];
  const todos = [0, 1, 2, 3, 4, 5, 6];

  const oficina = promedio(m, laborables, HORAS_OFICINA.desde, HORAS_OFICINA.hasta);
  const madrugada = promedio(m, todos, HORAS_MADRUGADA.desde, HORAS_MADRUGADA.hasta);
  const fin = promedio(m, finde, 0, 24);

  // Lo que hace el punto: si esto fuera mayor que uno, habría gente detrás.
  const razonNoche = oficina > 0 ? madrugada / oficina : 0;
  const razonFinde = oficina > 0 ? fin / oficina : 0;

  const resumen = [
    { label: t.week.office, value: oficina, ratio: null as number | null },
    { label: t.week.night, value: madrugada, ratio: razonNoche },
    { label: t.week.weekend, value: fin, ratio: razonFinde },
  ];

  return (
    <div className="panel p-4">
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <span className="rotulo">{t.week.title}</span>
        <span className="text-[10px] text-white/30">{t.week.utc}</span>
      </div>

      <div className="overflow-x-auto thin-scroll">
        <div className="min-w-[520px]">
          {/* eje de horas */}
          <div className="flex gap-[2px] pl-8 mb-1">
            {Array.from({ length: 24 }, (_, h) => (
              <div key={h} className="flex-1 text-center font-data text-[8px] text-white/25">
                {h % 3 === 0 ? h : ''}
              </div>
            ))}
          </div>

          {m.map((fila, d) => (
            <div key={d} className="flex gap-[2px] items-center mb-[2px]">
              <div className="w-8 shrink-0 font-data text-[9px] text-white/35">
                {t.week.days[d]}
              </div>
              {fila.map((v, h) => (
                <div
                  key={h}
                  className="flex-1 h-5 rounded-[2px] cursor-default"
                  style={{ background: color(v, max) }}
                  onMouseMove={(e) =>
                    tip.show(
                      e,
                      <div className="min-w-[150px]">
                        <div className="text-[11px] text-white/90">
                          {t.week.daysLong[d]}, {String(h).padStart(2, '0')}:00
                        </div>
                        <div className="font-data text-[15px] text-white mt-0.5">
                          {n(Math.round(v))}
                        </div>
                        <div className="text-[10px] text-white/45">{t.week.perHour}</div>
                        <div className="text-[9px] text-white/30 mt-1">
                          {t.week.observed(data.observed[d][h])}
                        </div>
                      </div>,
                    )
                  }
                  onMouseLeave={tip.hide}
                />
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-4">
        {resumen.map((r) => (
          <div key={r.label} className="rounded-lg bg-white/[0.03] p-2.5">
            <div className="cifra-chica">{n(Math.round(r.value))}</div>
            <div className="rotulo mt-0.5">{r.label}</div>
            {r.ratio !== null && (
              <div
                className="text-[10px] mt-1"
                style={{
                  color: r.ratio >= 1 ? 'var(--agent-coral)' : 'var(--neural-teal)',
                }}
              >
                {t.week.vsOffice(dec(r.ratio, 2))}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="text-[11px] text-white/55 leading-relaxed mt-3">
        {razonNoche >= 1 && razonFinde >= 1 ? t.week.verdictAutomated : t.week.verdictMixed}
      </div>

      <Tooltip content={tip.content} at={tip.at} />
    </div>
  );
}
