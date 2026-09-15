import type { ArchetypeData } from '../lib/api';
import { n, pct } from '../lib/format';
import { useI18n } from '../lib/i18n';

/**
 * Cuántas de las direcciones que golpearon la puerta pasaron cada etapa de una intrusión.
 *
 * Las tarjetas de arquetipos ya traen estos números, pero repartidos en tres tarjetas el lector
 * tiene que sostenerlos en la cabeza para ver la forma. Apilados en un embudo, la caída es la
 * imagen: la barra de "golpearon" es el ancho del panel y la de "se llevaron algo" es una astilla.
 *
 * Todos los números se derivan de los perfiles de arquetipos, así que esto no puede contradecir a
 * las tarjetas de abajo. Una segunda consulta devolvería totales apenas distintos, por motivos
 * difíciles de explicar a quien mira el panel.
 */

/**
 * Colores como tripletas y no como `var(--…)`.
 *
 * El degradado de cada barra necesita el mismo tono con dos opacidades, y a una variable CSS no se
 * le puede concatenar el alfa: `var(--neural-teal)55` no es color válido y la barra queda sin
 * fondo. Las tripletas son las mismas de la paleta, definidas en index.css.
 */
const TONO = {
  slate: '148,163,184',
  teal: '0,184,148',
  amber: '212,134,10',
  coral: '255,107,53',
} as const;

interface Paso {
  label: string;
  hint: string;
  value: number;
  /** Tripleta rgb, sin envolver: la barra la usa con dos alfas distintos. */
  rgb: string;
}

export default function AttackFunnel({ data }: { data: ArchetypeData }) {
  const { t } = useI18n();
  const p = data.perfiles;

  const total = data.direcciones_analizadas;
  const suma = (f: (a: (typeof p)[number]) => number) =>
    Math.round(p.reduce((s, a) => s + f(a), 0));

  // "Probó credenciales" son los que no se quedaron en el sondeo: el arquetipo de sondeo se define
  // justamente por no insistir con el acceso.
  const probaron = suma((a) => (a.nombre === 'Sondeo' ? 0 : a.direcciones));
  const entraron = suma((a) => (a.direcciones * a.pct_logro_acceso) / 100);
  const ejecutaron = suma((a) => (a.direcciones * a.pct_ejecuto_comandos) / 100);
  const bajaron = suma((a) => (a.direcciones * a.pct_descargo_archivo) / 100);

  const pasos: Paso[] = [
    {
      label: t.funnel.knocked,
      hint: t.funnel.knockedHint,
      value: total,
      rgb: TONO.slate,
    },
    {
      label: t.funnel.tried,
      hint: t.funnel.triedHint,
      value: probaron,
      rgb: TONO.teal,
    },
    {
      label: t.funnel.gotIn,
      hint: t.funnel.gotInHint,
      value: entraron,
      rgb: TONO.amber,
    },
    { label: t.funnel.ran, hint: t.funnel.ranHint, value: ejecutaron, rgb: TONO.amber },
    { label: t.funnel.took, hint: t.funnel.tookHint, value: bajaron, rgb: TONO.coral },
  ];

  return (
    <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
      <div className="text-[9px] uppercase tracking-wider text-white/35 mb-3">{t.funnel.title}</div>

      <div className="flex flex-col gap-2">
        {pasos.map((paso, i) => {
          const ancho = (paso.value / (total || 1)) * 100;
          const previo = i === 0 ? null : pasos[i - 1].value;
          // Cuánto sobrevive de un escalón al siguiente. Es el número que cuenta la historia:
          // el porcentaje sobre el total esconde dónde está la caída.
          const supervivencia = previo ? (paso.value / (previo || 1)) * 100 : null;

          return (
            <div key={paso.label}>
              <div className="flex items-baseline justify-between gap-2 mb-1">
                <span className="text-[11px] text-white/75">{paso.label}</span>
                <span className="font-data text-[11px] text-white/85">
                  {n(paso.value)}
                  <span className="text-white/30"> · {pct(paso.value, total, 1)}%</span>
                </span>
              </div>

              {/* Ancho mínimo visible: el último escalón es el 1 % del primero y con la proporción
                  exacta desaparecería, que es justo el dato que hay que poder ver. */}
              <div className="h-6 rounded-md bg-white/[0.04] overflow-hidden">
                <div
                  className="h-6 rounded-md transition-all duration-1000 flex items-center px-2"
                  style={{
                    width: `${Math.max(ancho, 1.6)}%`,
                    background: `linear-gradient(90deg, rgba(${paso.rgb},0.42), rgba(${paso.rgb},0.12))`,
                    borderRight: `2px solid rgb(${paso.rgb})`,
                  }}
                />
              </div>

              <div className="flex items-baseline justify-between gap-2 mt-1">
                <span className="text-[9px] text-white/35">{paso.hint}</span>
                {supervivencia !== null && (
                  <span className="font-data text-[9px] text-white/30">
                    {t.funnel.survives(supervivencia.toFixed(1).replace('.0', ''))}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="text-[11px] text-white/55 leading-relaxed mt-4">
        {t.funnel.lesson(n(total), n(bajaron), pct(bajaron, total, 2))}
      </div>
    </div>
  );
}
