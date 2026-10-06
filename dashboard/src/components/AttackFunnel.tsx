import type { ArchetypeData } from '../lib/api';
import { n, pct } from '../lib/format';
import { useI18n } from '../lib/i18n';
import ManoAlzada from './ManoAlzada';

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
 * Colores como tripletas y no como variables de CSS.
 *
 * El degradado de cada barra necesita el mismo tono con dos opacidades, y a una variable CSS no se
 * le puede concatenar el alfa: la barra quedaría sin fondo. Las tripletas son las mismas de la
 * paleta, definidas en index.css.
 */
const TONO = {
  slate: '148,163,184',
  teal: '0,184,148',
  amber: '212,134,10',
  coral: '255,107,53',
} as const;

// Ancho mínimo visible: el último escalón es el 1 % del primero y con la proporción exacta
// desaparecería, que es justo el dato que hay que poder ver.
const ANCHO_MINIMO = 2.2;

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
    { label: t.funnel.knocked, hint: t.funnel.knockedHint, value: total, rgb: TONO.slate },
    { label: t.funnel.tried, hint: t.funnel.triedHint, value: probaron, rgb: TONO.teal },
    { label: t.funnel.gotIn, hint: t.funnel.gotInHint, value: entraron, rgb: TONO.amber },
    { label: t.funnel.ran, hint: t.funnel.ranHint, value: ejecutaron, rgb: TONO.amber },
    { label: t.funnel.took, hint: t.funnel.tookHint, value: bajaron, rgb: TONO.coral },
  ];

  const ancho = (v: number) => Math.max((v / (total || 1)) * 100, ANCHO_MINIMO);

  // El escalón donde se pierde la mayor parte de lo que venía: es el que se anota a mano.
  const supervivencias = pasos.map((paso, i) =>
    i === 0 ? 1 : paso.value / (pasos[i - 1].value || 1),
  );
  const peorCaida = supervivencias.reduce(
    (peor, s, i) => (i > 0 && s < supervivencias[peor] ? i : peor),
    1,
  );

  return (
    <div className="pliego">
      <div className="rotulo mb-4">{t.funnel.title}</div>

      <div className="flex flex-col">
        {pasos.map((paso, i) => {
          const actual = ancho(paso.value);
          const previo = i === 0 ? null : ancho(pasos[i - 1].value);
          // Cuánto sobrevive de un escalón al siguiente. Es el número que cuenta la historia:
          // el porcentaje sobre el total esconde dónde está la caída.
          const supervivencia = i === 0 ? null : supervivencias[i] * 100;

          return (
            <div key={paso.label}>
              {/* El tramo que une un escalón con el siguiente, angostándose como un embudo */}
              {/* En un teléfono el rótulo queda entre dos barras y el tramo no las uniría, así que
                  ahí no se dibuja. */}
              {previo !== null && (
                <div className="hidden sm:grid sm:grid-cols-[190px_minmax(0,1fr)_120px] gap-x-4">
                  <span className="hidden sm:block" />
                  <div className="relative h-5">
                    <div
                      className="absolute inset-0"
                      style={{
                        background: `linear-gradient(180deg, rgba(${pasos[i - 1].rgb},0.14), rgba(${paso.rgb},0.14))`,
                        clipPath: `polygon(${(100 - previo) / 2}% 0, ${(100 + previo) / 2}% 0, ${(100 + actual) / 2}% 100%, ${(100 - actual) / 2}% 100%)`,
                      }}
                    />
                    {i === peorCaida && supervivencia !== null && (
                      <ManoAlzada
                        trazos={[
                          {
                            tipo: 'elipse',
                            x: 50,
                            y: 50,
                            ancho: Math.max(previo * 0.55, 12),
                            alto: 150,
                          },
                        ]}
                        notas={[
                          {
                            x: 50 + Math.max(previo * 0.3, 8) + 2,
                            y: -10,
                            texto: t.funnel.noteDrop(n(Math.round(100 - supervivencia))),
                            ancho: 240,
                          },
                        ]}
                      />
                    )}
                  </div>
                  <span className="hidden sm:block" />
                </div>
              )}

              <div className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[190px_minmax(0,1fr)_120px] gap-x-4 gap-y-1 items-center">
                <div className="min-w-0">
                  <div className="text-[12px] text-white/80">{paso.label}</div>
                  <div className="text-[9.5px] text-white/35 leading-snug hidden sm:block">
                    {paso.hint}
                  </div>
                </div>
                <div className="col-span-2 sm:col-span-1 order-3 sm:order-none h-7 relative mb-2 sm:mb-0">
                  <div
                    className="absolute inset-y-0 rounded-md transition-all duration-1000"
                    style={{
                      left: `${(100 - actual) / 2}%`,
                      width: `${actual}%`,
                      background: `linear-gradient(90deg, rgba(${paso.rgb},0.14), rgba(${paso.rgb},0.5), rgba(${paso.rgb},0.14))`,
                      boxShadow: `inset 0 0 0 1px rgba(${paso.rgb},0.55)`,
                    }}
                  />
                  {i === peorCaida && supervivencia !== null && (
                    <div className="sm:hidden absolute inset-0">
                      <ManoAlzada
                        trazos={[{ tipo: 'elipse', x: 50, y: 50, ancho: actual + 8, alto: 150 }]}
                        notas={[
                          {
                            x: 50 + actual / 2 + 7,
                            y: 8,
                            texto: t.funnel.noteDrop(n(Math.round(100 - supervivencia))),
                            ancho: 200,
                          },
                        ]}
                      />
                    </div>
                  )}
                </div>
                <div className="text-right">
                  <div className="font-data text-[12px] text-white/85">{n(paso.value)}</div>
                  <div className="font-data text-[9.5px] text-white/35">
                    {t.funnel.ofTotal(pct(paso.value, total, 1))}
                  </div>
                  {i > 0 && (
                    <div className="font-data text-[9.5px] text-white/25">
                      {t.funnel.ofPrevious(pct(paso.value, pasos[i - 1].value, 1))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="text-[11px] text-white/55 leading-relaxed mt-5">
        {t.funnel.lesson(n(total), n(bajaron), pct(bajaron, total, 2))}
      </div>
    </div>
  );
}
