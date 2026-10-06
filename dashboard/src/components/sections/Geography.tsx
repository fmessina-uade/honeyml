import { useState } from 'react';
import Globo from '../Globe';
import type { Geography as GeoData } from '../../lib/api';
import Reveal from '../Reveal';
import ManoAlzada from '../ManoAlzada';
import { Palabras } from '../Titular';
import { n, nombreDePais, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';

/**
 * De dónde vienen los ataques: por país, y por la red que efectivamente opera la dirección.
 *
 * El país solo es la mitad más débil. Lo que separa un servidor alquilado de una conexión hogareña
 * es el sistema autónomo, así que se muestran los dos lado a lado y la sección está escrita
 * alrededor de esa comparación y no de un ranking de banderas.
 */

/**
 * El país como su código de dos letras, en un recuadro. Las banderas con emoji dependen del sistema:
 * en Windows se ven como dos letras sueltas, así que el panel muestra directamente el código, igual
 * en todas partes.
 */
function Codigo({ iso }: { iso: string }) {
  return (
    <span className="inline-flex items-center justify-center font-data text-[9px] leading-none w-6 h-4 rounded-[3px] ring-1 ring-white/15 text-white/60 shrink-0">
      {iso.length === 2 ? iso.toUpperCase() : '?'}
    </span>
  );
}

export default function Geography({ data }: { data: GeoData }) {
  const { t } = useI18n();
  // Un solo país seleccionado a la vez: el globo gira hasta él y la fila queda resaltada. Volver a
  // tocarlo deselecciona y el giro continuo se retoma.
  const [pais, setPais] = useState<string | null>(null);

  const elegido = pais ? (data.countries.find((c) => c.country === pais) ?? null) : null;

  const maxPais = Math.max(...data.countries.map((c) => c.count), 1);
  const maxAs = Math.max(...data.autonomous_systems.map((a) => a.count), 1);

  // Los eventos por dirección son la pista: un país puede liderar en volumen y ser cuatro equipos.
  //
  // Formateado con el helper del proyecto y no con toLocaleString directo: ese cae en el locale del
  // navegador, y así apareció "1,537" al lado de "252.137" en la misma línea. El helper sigue el
  // selector de idioma, así que los dos números quedan consistentes.
  const porDireccion = (count: number, sources: number) => n(Math.round(count / (sources || 1)));

  // El país que más eventos junta por dirección es la lección de la sección hecha dato: lidera en
  // insistencia con pocas máquinas. Es el que se subraya a mano en la tabla.
  const insistente = data.countries.reduce<(typeof data.countries)[number] | null>(
    (mejor, c) =>
      c.sources > 0 && (!mejor || c.count / c.sources > mejor.count / (mejor.sources || 1))
        ? c
        : mejor,
    null,
  );

  const panelElegido = elegido ? (
    <>
      <div className="flex flex-wrap items-end gap-x-4 gap-y-3 mb-4">
        {[
          { label: t.geography.addresses, value: n(elegido.sources) },
          {
            label: t.geography.perAddressShort,
            value: porDireccion(elegido.count, elegido.sources),
          },
          {
            label: t.geography.ofLocated,
            value: `${pct(elegido.count, data.with_geo, 1)}%`,
          },
        ].map((m, i) => (
          <div key={m.label} className="flex items-end gap-4">
            {i > 0 && <span className="barra-oblicua" aria-hidden />}
            <div>
              <div className="cifra-fina">{m.value}</div>
              <div className="rotulo mt-1.5">{m.label}</div>
            </div>
          </div>
        ))}
      </div>
      {t.geography.selected(nombreDePais(elegido.iso, elegido.country))}
    </>
  ) : (
    t.geography.pickHint
  );

  return (
    <section className="flex flex-col gap-14">
      {/* La presentación: el globo en grande, y al lado el titular y el país elegido.
          El globo y la tabla son un solo control: elegir en cualquiera de los dos mueve al otro. */}
      <div className="presentacion presentacion-globo">
        <div className="relative max-w-[1320px] mx-auto px-4 md:px-8 pt-12 sm:pt-16 pb-10 grid lg:grid-cols-[minmax(0,1fr)_minmax(0,540px)] gap-8 lg:gap-12 items-center">
          <div className="min-w-0 order-2 lg:order-1">
            <span className="ceja section-in">{t.geography.heroBadge}</span>
            <h1 className="titular-pesado mt-5">
              <Palabras texto={t.nav.origen} />
            </h1>
            <p className="portada-bajada section-in">{t.lead.origen}</p>
            <div className="text-[12.5px] text-white/55 leading-relaxed mt-8 max-w-[34rem] min-h-[96px]">
              {panelElegido}
              <div className="text-[11px] text-white/35 mt-2">{t.geography.dragHint}</div>
            </div>
          </div>
          <div className="relative aspect-square w-full max-w-[540px] mx-auto order-1 lg:order-2">
            <div className="globo-halo" aria-hidden />
            <Globo countries={data.countries} selected={pais} onSelect={setPais} />

            {/* El nombre va sobre el globo y no al costado: al elegir un país la mirada ya está
                acá, siguiendo el giro, y leerlo en otro lado obliga a buscarlo. Sin capturar el
                puntero, para no romper el arrastre que pasa por debajo. */}
            {elegido && (
              <div
                key={elegido.country}
                className="pais-rotulo pointer-events-none absolute inset-x-0 bottom-2 px-3 text-center"
              >
                <div className="mb-1.5">
                  <Codigo iso={elegido.iso} />
                </div>
                <div className="titular-pesado pais-grande text-balance">
                  {nombreDePais(elegido.iso, elegido.country)}
                </div>
                <div className="font-data text-[11px] text-[var(--agent-coral)] mt-1.5">
                  {n(elegido.count)}{' '}
                  <span className="text-white/40">{t.geography.eventsShort}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <Reveal>
        <figure className="cita" style={{ borderColor: 'var(--neural-teal)' }}>
          <span className="ceja">{t.geography.byAs}</span>
          <blockquote className="mt-4">{t.geography.lesson}</blockquote>
        </figure>
      </Reveal>

      {/* Los dos rankings, numerados y sin caja */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
        <Reveal>
          <div className="pliego">
            <span className="ceja">{t.geography.byCountry}</span>
            <div className="flex flex-col mt-5">
              {data.countries.map((c, i) => {
                const activo = pais === c.country;
                const subrayado = insistente === c && data.countries.length > 2;
                return (
                  <button
                    key={c.country}
                    onClick={() => setPais(activo ? null : c.country)}
                    data-activo={activo ? 'si' : undefined}
                    className="ranking-fila"
                  >
                    <span className="ranking-n">{String(i + 1).padStart(2, '0')}</span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline justify-between gap-3">
                        <span className="flex items-center gap-2 min-w-0">
                          <Codigo iso={c.iso} />
                          <span className="geist text-[15px] tracking-tight truncate text-white/90">
                            {nombreDePais(c.iso, c.country)}
                          </span>
                        </span>
                        <span className="font-data text-[11px] text-white/55 shrink-0">
                          {n(c.count)}
                        </span>
                      </span>
                      <span className="block h-1 rounded bg-white/5 mt-2 overflow-hidden">
                        <span
                          className="block h-1 rounded transition-all duration-700"
                          style={{
                            width: `${(c.count / maxPais) * 100}%`,
                            background: activo ? 'var(--agent-coral)' : 'var(--neural-teal)',
                          }}
                        />
                      </span>
                      <span className="block text-[10.5px] text-white/35 mt-1.5">
                        {t.geography.perAddress(porDireccion(c.count, c.sources))},{' '}
                        {t.geography.fromAddresses(n(c.sources))}
                      </span>
                    </span>
                    {subrayado && (
                      <ManoAlzada
                        trazos={[{ tipo: 'subrayado', x1: 8, x2: 40, y: 99 }]}
                        notas={[{ x: 66, y: 72, texto: t.geography.noteLoud, ancho: 220 }]}
                      />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </Reveal>

        <Reveal delay={120}>
          <div className="pliego">
            <span className="ceja">{t.geography.byAs}</span>
            <div className="flex flex-col mt-5">
              {data.autonomous_systems.map((a, i) => (
                <div key={a.organization} className="ranking-fila">
                  <span className="ranking-n">{String(i + 1).padStart(2, '0')}</span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-3">
                      <span className="geist text-[15px] tracking-tight truncate text-white/90">
                        {a.organization}
                      </span>
                      <span className="font-data text-[11px] text-white/55 shrink-0">
                        {n(a.count)}
                      </span>
                    </span>
                    <span className="block h-1 rounded bg-white/5 mt-2 overflow-hidden">
                      <span
                        className="block h-1 rounded transition-all duration-700"
                        style={{
                          width: `${(a.count / maxAs) * 100}%`,
                          background: 'var(--honey-amber)',
                        }}
                      />
                    </span>
                    <span className="block text-[10.5px] text-white/35 mt-1.5">
                      {t.geography.fromAddresses(n(a.sources))}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </div>

      {/* La cobertura se dice y no se supone: los porcentajes de arriba se calculan sobre lo que se
          pudo resolver. */}
      <Reveal>
        <p className="text-[11px] text-white/40 leading-relaxed max-w-[64rem]">
          {t.geography.coverage(
            pct(data.with_geo, data.events, 1),
            pct(data.with_asn, data.events, 1),
          )}
        </p>
      </Reveal>
    </section>
  );
}
